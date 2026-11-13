'use strict';
// Fixed in-cluster, credential-free readiness endpoints. No redirects or body logs.
const http = require('node:http');
const endpoints = {
  ferretdb: 'http://ferretdb.spotify.svc.cluster.local:8088/debug/readyz',
  spotify: 'http://server.spotify.svc.cluster.local:8080/',
};
function probe(url) {
  return new Promise((resolve) => {
    const req = http.get(url, { agent: false }, (res) => {
      res.resume();
      clearTimeout(timer);
      resolve(res.statusCode === 200);
    });
    const timer = setTimeout(() => req.destroy(), 4000);
    req.on('error', () => { clearTimeout(timer); resolve(false); });
  });
}
module.exports = { probe };
if (require.main === module) {
  const url = endpoints[process.argv[2]];
  if (!url) process.exit(1);
  probe(url).then((ok) => process.exit(ok ? 0 : 1));
}
