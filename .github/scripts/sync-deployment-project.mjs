import { readFile } from "node:fs/promises";

const organization = "ProjectLanternDI3P1P2";
const services = new Map([
  ["combat", { repository: "combat-backend", deployment: "combat-api", container: "api" }],
  ["dungeon", { repository: "dungeon-backend", deployment: "dungeon-api", container: "api" }],
  ["player", { repository: "player-backend", deployment: "player-api", container: "player-api" }],
  ["rewards", { repository: "reward-backend", deployment: "rewards-api", container: "api" }],
  ["leaderboard", { repository: "leaderboard-backend", deployment: "leaderboard-api", container: "api" }],
  ["frontend-game", { repository: "frontend-game", deployment: "frontend-game", container: "frontend-game" }],
  ["frontend-public", { repository: "frontend-public", deployment: "frontend-public", container: "frontend-public" }],
]);
const repositories = new Set(Array.from(services.values(), ({ repository }) => repository));
const fields = new Map([
  ["Latest release", "TEXT"],
  ["GitOps image", "TEXT"],
  ["Confirmed image", "TEXT"],
  ["Argo CD status", "TEXT"],
  ["Last checked", "TEXT"],
]);

async function readDesiredImage(application) {
  const path = `apps/${application}/overlays/k3s/kustomization.yaml`;
  const manifest = await readFile(path, "utf8");
  const imagesBlock = manifest.match(/^images:[^\S\n]*\n((?:^[ \t]+[^\n]*\n?)*)/m)?.[1] ?? "";
  const entries = imagesBlock.split(/^\s*- name:/m).slice(1);
  const { repository } = services.get(application);
  const images = entries.flatMap((entry) => {
    const name = entry.match(/^[ \t]*newName:[ \t]*(\S+)/m)?.[1]
      ?? entry.split("\n")[0].trim();
    const tag = entry.match(/^[ \t]*newTag:[ \t]*(\S+)/m)?.[1];
    const digest = entry.match(/^[ \t]*digest:[ \t]*(\S+)/m)?.[1];
    if (!name?.endsWith(`/${repository}`) || (!tag && !digest)) return [];
    return [`${name}${tag ? `:${tag}` : ""}${digest ? `@${digest}` : ""}`];
  });
  if (images.length !== 1) throw new Error(`Expected one versioned API image in ${path}.`);
  return images[0];
}

async function request(url, token, body) {
  const response = await fetch(url, {
    method: body ? "POST" : "GET",
    headers: {
      Accept: "application/json",
      Authorization: `Bearer ${token}`,
      ...(body && { "Content-Type": "application/json" }),
    },
    body: body && JSON.stringify(body),
    signal: AbortSignal.timeout(15_000),
    redirect: "error",
  });
  return response;
}

async function latestRelease(repository, token) {
  const url = `https://api.github.com/repos/${organization}/${repository}/releases?per_page=100`;
  let nextUrl = url;
  while (nextUrl) {
    const response = await request(nextUrl, token);
    if (!response.ok) throw new Error(`${repository}: releases returned HTTP ${response.status}.`);
    const releases = await response.json();
    const release = releases.find((entry) =>
      !entry.draft && !entry.prerelease && /^v\d+\.\d+\.\d+$/.test(entry.tag_name)
    );
    if (release) return release.tag_name;
    const next = response.headers.get("link")?.match(/<([^>]+)>; rel="next"/)?.[1];
    if (next && new URL(next).origin !== new URL(url).origin) {
      throw new Error("Unexpected GitHub pagination host.");
    }
    nextUrl = next;
  }
  return "Aucune release applicative";
}

async function observeDeployment(application) {
  const base = process.env.DEPLOYMENT_ARGOCD_URL?.replace(/\/$/, "");
  const token = process.env.DEPLOYMENT_ARGOCD_TOKEN;
  if (!base && !token) return ["Non vérifiée", "Accès Argo CD non configuré"];
  if (!base || !token) throw new Error("Configure DEPLOYMENT_ARGOCD_URL and DEPLOYMENT_ARGOCD_TOKEN together.");
  if (new URL(base).protocol !== "https:") throw new Error("DEPLOYMENT_ARGOCD_URL must use HTTPS.");

  const url = `${base}/api/v1/applications/${application}`;
  const resource = new URLSearchParams({
    namespace: application,
    resourceName: services.get(application).deployment,
    group: "apps",
    version: "v1",
    kind: "Deployment",
  });

  try {
    const response = await request(url, token);
    if (!response.ok) return ["Non vérifiée", `Argo CD HTTP ${response.status}`];
    const { status } = await response.json();
    const label = `${status?.sync?.status ?? "Unknown"} / ${status?.health?.status ?? "Unknown"}`;

    const deploymentResponse = await request(`${url}/resource?${resource}`, token);
    if (!deploymentResponse.ok) {
      return ["Non vérifiée", `${label} · Deployment HTTP ${deploymentResponse.status}`];
    }
    const { manifest } = await deploymentResponse.json();
    const deployment = JSON.parse(manifest);
    const replicas = deployment.spec.replicas ?? 1;
    const current = deployment.status;
    const image = deployment.spec.template.spec.containers.find(({ name }) => name === services.get(application).container)?.image;
    const fullyRolledOut = image && replicas > 0 &&
      current?.observedGeneration === deployment.metadata.generation &&
      current.replicas === replicas &&
      current.updatedReplicas === replicas &&
      current.availableReplicas === replicas;

    return [fullyRolledOut ? image : "Non vérifiée", label];
  } catch {
    return ["Non vérifiée", "Argo CD inaccessible ou réponse invalide"];
  }
}

async function graphql(query, variables, token) {
  const response = await request("https://api.github.com/graphql", token, { query, variables });
  if (!response.ok) throw new Error(`GitHub Projects returned HTTP ${response.status}.`);
  const result = await response.json();
  if (result.errors?.length) throw new Error(result.errors.map(({ message }) => message).join("; "));
  return result.data;
}

async function loadProject(number, token) {
  const data = await graphql(`query($org: String!, $number: Int!) {
    organization(login: $org) {
      projectV2(number: $number) {
        id
        fields(first: 100) {
          nodes { ... on ProjectV2Field { id name dataType } }
        }
      }
    }
  }`, { org: organization, number }, token);
  const project = data.organization?.projectV2;
  if (!project) throw new Error(`Project ${organization}/${number} not found or inaccessible.`);

  const fieldIds = new Map();
  for (const [name, type] of fields) {
    const field = project.fields.nodes.find((entry) => entry?.name === name);
    if (field?.dataType !== type) throw new Error(`Create the text field "${name}" in the Project.`);
    fieldIds.set(name, field.id);
  }
  return { id: project.id, fieldIds };
}

async function loadRows(projectId, token) {
  const rows = new Map();
  let cursor = null;
  do {
    const { node } = await graphql(`query($id: ID!, $cursor: String) {
      node(id: $id) {
        ... on ProjectV2 {
          items(first: 100, after: $cursor) {
            pageInfo { endCursor hasNextPage }
            nodes { id content { ... on DraftIssue { title } } }
          }
        }
      }
    }`, { id: projectId, cursor }, token);
    for (const item of node.items.nodes) {
      const title = item?.content?.title;
      if (!repositories.has(title)) continue;
      if (rows.has(title)) throw new Error(`Duplicate draft rows named "${title}".`);
      rows.set(title, item.id);
    }
    cursor = node.items.pageInfo.hasNextPage ? node.items.pageInfo.endCursor : null;
  } while (cursor);
  return rows;
}

async function createRow(projectId, title, token) {
  const data = await graphql(`mutation($projectId: ID!, $title: String!) {
    addProjectV2DraftIssue(input: { projectId: $projectId, title: $title }) {
      projectItem { id }
    }
  }`, { projectId, title }, token);
  return data.addProjectV2DraftIssue.projectItem.id;
}

async function updateRow(project, itemId, values, token) {
  for (const [name, text] of values) {
    await graphql(`mutation($projectId: ID!, $itemId: ID!, $fieldId: ID!, $text: String!) {
      updateProjectV2ItemFieldValue(input: {
        projectId: $projectId, itemId: $itemId, fieldId: $fieldId, value: { text: $text }
      }) { projectV2Item { id } }
    }`, { projectId: project.id, itemId, fieldId: project.fieldIds.get(name), text }, token);
  }
}

async function main() {
  if (process.argv.includes("--check-manifests")) {
    for (const [application, { repository }] of services) {
      console.log(`${repository}: ${await readDesiredImage(application)}`);
    }
    return;
  }

  const number = Number(process.env.DEPLOYMENT_PROJECT_NUMBER);
  const token = process.env.DEPLOYMENT_PROJECT_TOKEN;
  if (!Number.isInteger(number) || number < 1 || !token) {
    throw new Error("Configure DEPLOYMENT_PROJECT_NUMBER and the BOT_TOKEN Actions secret.");
  }

  const project = await loadProject(number, token);
  const rows = await loadRows(project.id, token);
  const snapshots = await Promise.all(Array.from(services, async ([application, { repository }]) => {
    const [expected, release] = await Promise.all([
      readDesiredImage(application),
      latestRelease(repository, token),
    ]);
    const [confirmed, status] = await observeDeployment(application);
    return { repository, expected, release, confirmed, status };
  }));

  for (const { repository, expected, release, confirmed, status } of snapshots) {
    const row = rows.get(repository) ?? await createRow(project.id, repository, token);
    await updateRow(project, row, [
      ["Latest release", release],
      ["GitOps image", expected],
      ["Confirmed image", confirmed],
      ["Argo CD status", status],
      ["Last checked", new Date().toISOString()],
    ], token);
    console.log(`${repository}: ${release}; ${expected}; ${status}`);
  }
}

await main();
