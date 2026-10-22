import { readFile, writeFile } from "node:fs/promises";

const image = process.env.IMAGE ?? "";
const tag = process.env.TAG ?? "";
const sourceRepository = process.env.SOURCE_REPOSITORY ?? "";
const sourceRevision = process.env.SOURCE_REVISION ?? "";
const expectedImage = "10.4.111.200:18443/lantern/keycloak-theme";
const expectedRepository = "ProjectLanternDI3P1P2/frontend-game";
const path = "platform/keycloak/deployment-keycloak.yaml";
const regexEscapeReplacement = String.raw`\$&`;

if (image !== expectedImage) throw new Error("Unexpected Keycloak theme image");
if (sourceRepository !== expectedRepository) throw new Error("Unexpected source repository");
if (!/^v\d+\.\d+\.\d+$/.test(tag)) throw new Error("Invalid immutable tag");
if (!/^[0-9a-f]{40}$/.test(sourceRevision)) throw new Error("Invalid source revision");

const input = await readFile(path, "utf8");
const escapedImage = expectedImage.replace(/[.*+?^${}()|[\]\\]/g, regexEscapeReplacement);
const matches = input.match(new RegExp(String.raw`image: ${escapedImage}:[^\r\n]+`, "g")) ?? [];
if (matches.length !== 1) throw new Error(`Expected one Keycloak theme image in ${path}`);

await writeFile(path, input.replace(matches[0], `image: ${image}:${tag}`), "utf8");
