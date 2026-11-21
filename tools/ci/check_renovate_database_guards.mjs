/** Run with Node and the path to an installed Renovate package directory. */
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const packageRoot = process.argv[2];
assert(packageRoot, 'Usage: node tools/ci/check_renovate_database_guards.mjs /path/to/node_modules/renovate');
const moduleUrl = (path) => pathToFileURL(resolve(packageRoot, 'dist', path)).href;
const { extractPackageFile } = await import(moduleUrl('modules/manager/kubernetes/extract.js'));
const { applyPackageRules } = await import(moduleUrl('util/package-rules/index.js'));
const root = new URL('../../', import.meta.url);
const config = JSON.parse(await readFile(new URL('renovate.json', root), 'utf8'));
const cases = [
  ['keycloak/stateful-set-keycloak-postgres.yaml', '18.99', '19.0'],
  ['keycloak/stateful-set-keycloak.yaml', '18.99', '19.0'],
  ['bitwarden/stateful-set-bitwarden-postgres.yaml', '19.7', '20.0'],
  ['mastodon/stateful-set-mastodon-postgres.yaml', '19.7', '20.0'],
  ['dawarich/stateful-set-dawarich-postgres.yaml', '18-3.7', '19-3.7'],
  ['immich/stateful-set-immich-postgres.yaml', '18-vectorchord1.1.1', '19-vectorchord1.1.1'],
  ['your-spotify/stateful-set-ferretdb-postgres.yaml', '17-0.107.0', '18-0.107.0'],
  ['firefox-sync/deployment-mariadb.yaml', '13.1.7', '14.0.0'],
  ['firefox-sync/deployment-firefox-sync.yaml', '13.1.7', '14.0.0'],
  ['nextcloud/deployment-mysql-nextcloud.yaml', '13.1.7', '14.0.0'],
  ['wordpress/deployment-mysql-wordpress.yaml', '13.1.7', '14.0.0'],
];
for (const [file, allowed, denied] of cases) {
  const source = await readFile(new URL(file, root), 'utf8');
  const deps = extractPackageFile(source, file, config).deps.filter(
    (dep) => dep.datasource === 'docker' && /\/(postgres|postgis|postgres-documentdb|mariadb)$/.test(dep.depName),
  );
  assert(deps.length, `${file}: no database dependencies extracted`);
  for (const dep of deps) {
    const result = await applyPackageRules({
      ...dep, manager: 'kubernetes', packageFile: file, packageRules: config.packageRules,
    });
    assert(result.allowedVersions, `${file}: missing version restriction for ${dep.depName}`);
    const pattern = new RegExp(result.allowedVersions.slice(1, -1));
    assert(pattern.test(dep.currentValue), `${file}: rejected current tag ${dep.currentValue}`);
    assert(pattern.test(allowed), `${file}: rejected ${allowed}`);
    assert(!pattern.test(denied), `${file}: permitted ${denied}`);
  }
}
console.log(`Passed ${cases.length} database guards using Renovate extraction and rule matching`);
