import { readFile, writeFile } from "node:fs/promises";

const applications = {
  combat: {
    image: "registry.lantern.diiage/lantern/combat-backend",
    repository: "ProjectLanternDI3P1P2/combat-backend",
  },
  dungeon: {
    image: "registry.lantern.diiage/lantern/dungeon-backend",
    repository: "ProjectLanternDI3P1P2/dungeon-backend",
  },
  "frontend-game": {
    image: "registry.lantern.diiage/lantern/frontend-game",
    repository: "ProjectLanternDI3P1P2/frontend-game",
  },
  "frontend-public": {
    image: "registry.lantern.diiage/lantern/frontend-public",
    repository: "ProjectLanternDI3P1P2/frontend-public",
  },
  player: {
    image: "registry.lantern.diiage/lantern/player-backend",
    repository: "ProjectLanternDI3P1P2/player-backend",
  },
  leaderboard: {
    image: "registry.lantern.diiage/lantern/leaderboard-backend",
    repository: "ProjectLanternDI3P1P2/leaderboard-backend",
  },
  rewards: {
    image: "registry.lantern.diiage/lantern/reward-backend",
    repository: "ProjectLanternDI3P1P2/reward-backend",
  },
};

const application = process.env.APPLICATION ?? "";
const image = process.env.IMAGE ?? "";
const tag = process.env.TAG ?? "";
const sourceRepository = process.env.SOURCE_REPOSITORY ?? "";
const sourceRevision = process.env.SOURCE_REVISION ?? "";
const expected = applications[application];

if (!expected) throw new Error(`Unsupported application: ${application}`);
if (image !== expected.image) throw new Error(`Unexpected image for ${application}`);
if (sourceRepository !== expected.repository) throw new Error(`Unexpected source repository for ${application}`);
if (!/^dev-[0-9a-f]{12}$/.test(tag)) throw new Error(`Invalid immutable tag: ${tag}`);
if (!/^[0-9a-f]{40}$/.test(sourceRevision)) throw new Error("Invalid source revision");

const path = `apps/${application}/overlays/k3s/kustomization.yaml`;
const input = await readFile(path, "utf8");
const lines = input.split(/(?<=\n)/);
const imageIndexes = lines.flatMap((line, index) => {
  const value = line.trim();
  return value === `- name: ${image}` || value === `newName: ${image}` ? [index] : [];
});
if (imageIndexes.length !== 1) throw new Error(`Expected one image entry in ${path}`);

let tagIndex = -1;
for (let index = imageIndexes[0] + 1; index < lines.length; index += 1) {
  const value = lines[index].trim();
  if (value.startsWith("- name:")) break;
  if (value.startsWith("newTag:")) {
    tagIndex = index;
    break;
  }
}
if (tagIndex < 0) throw new Error(`newTag entry not found in ${path}`);
lines[tagIndex] = lines[tagIndex].replace(/newTag:\s*[^\r\n]+/, `newTag: ${tag}`);
const output = lines.join("");
await writeFile(path, output, "utf8");
