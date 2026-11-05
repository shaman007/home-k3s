#!/usr/bin/env python3
"""Migrate selected internal OIDC URL settings, preserving secrets and auth policy."""
import argparse,json,re,runpy
from pathlib import Path
import urllib.request
ROOT=Path(__file__).resolve().parents[2]
SSO='https://sso.andreybondarenko.com'
BAO='https://openbao.int.andreybondarenko.com'
ACTIVE={'argocd','grafana','headlamp','openbao','traefik-admin'}
LEGACY={'graphana','vault'}

def request(url,headers,method='GET',body=None):
 data=None if body is None else json.dumps(body).encode()
 with urllib.request.urlopen(urllib.request.Request(url,data=data,method=method,headers={**headers,'Content-Type':'application/json'}),timeout=30) as response:
  raw=response.read();return json.loads(raw) if raw else None

def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--phase',choices=['add','finalize'],default='add')
 parser.add_argument('--write',action='store_true')
 args=parser.parse_args()
 inventory=json.loads((ROOT/'docs/migrations/letsencrypt-internal/inventory.json').read_text())
 mapping={old:new for c in inventory['certificates'] if not c['canary'] for old,new in zip(c['old_names'],c['new_names'])}
 def convert(value):
  for old,new in mapping.items(): value=re.sub(r'(?<![a-zA-Z0-9_.-])'+re.escape(old)+r'(?![a-zA-Z0-9_.-])',new,value)
  return value
 def urls(values):
  converted=[convert(v) for v in values]
  return list(dict.fromkeys(values+converted if args.phase=='add' else converted))
 helper=runpy.run_path(str(ROOT/'tools/provision-traefik-security.py'))
 headers={'Authorization':'Bearer '+helper['keycloak_token']()}
 endpoint=SSO+'/admin/realms/master/clients'
 for client in request(endpoint+'?max=100',headers):
  cid=client['clientId']
  if cid not in ACTIVE|LEGACY:continue
  if cid in LEGACY and args.phase=='add':continue
  url=endpoint+'/'+client['id']
  current=request(url,headers)
  payload={}
  if cid in LEGACY:
   sessions=request(url+'/user-sessions?max=1',headers)
   if sessions:raise RuntimeError('Legacy client has active sessions; retirement needs review')
   payload={'enabled':False,'redirectUris':[],'webOrigins':[],'rootUrl':'','baseUrl':'','adminUrl':'',
            'attributes':{**current.get('attributes',{}),'post.logout.redirect.uris':''}}
  else:
   for key in ['redirectUris','webOrigins']:
    old=current.get(key,[]);new=urls(old)
    if new!=old:payload[key]=new
   attributes=current.get('attributes',{})
   logout=attributes.get('post.logout.redirect.uris')
   if logout:
    new='##'.join(urls(logout.split('##')))
    if new!=logout:payload['attributes']={**attributes,'post.logout.redirect.uris':new}
   if args.phase=='finalize':
    for key in ['rootUrl','baseUrl','adminUrl']:
     if current.get(key) and convert(current[key])!=current[key]:payload[key]=convert(current[key])
  if not payload:print(cid+': already matches');continue
  if args.write:
   request(url,headers,'PUT',payload)
   actual=request(url,headers)
   for k,v in payload.items():
    matches=set(actual.get(k,[]))==set(v) if isinstance(v,list) else actual.get(k)==v
    if not matches:raise RuntimeError('Client URL verification failed for '+cid+'/'+k)
  print(cid+': '+('updated ' if args.write else 'planned ')+', '.join(payload))
 root=(Path.home()/'.codex/skills/vault-operator/root-token.txt').read_text().splitlines()[0]
 bh={'X-Vault-Token':root}
 role_url=BAO+'/v1/auth/oidc/role/keycloak'
 role=request(role_url,bh)['data'];desired=urls(role.get('allowed_redirect_uris',[]))
 if desired!=role.get('allowed_redirect_uris',[]):
  if args.write:
   request(role_url,bh,'POST',{**role,'allowed_redirect_uris':desired})
   actual=request(role_url,bh)['data']
   if actual['allowed_redirect_uris']!=desired:raise RuntimeError('OpenBao redirects did not persist')
   for key in ['user_claim','bound_audiences','bound_claims','token_policies','role_type']:
    before=role.get(key);after=actual.get(key)
    if before in (None,[]) and after in (None,[]):continue
    equal=set(before)==set(after) if isinstance(before,list) and isinstance(after,list) else before==after
    if not equal:raise RuntimeError('OpenBao auth policy field changed: '+key)
  print('OpenBao keycloak OIDC role: '+('updated' if args.write else 'planned')+' exact callback list')
 else:print('OpenBao OIDC role: already matches')

if __name__=='__main__':
 try:main()
 except Exception as exc:raise SystemExit(str(exc) if type(exc) is RuntimeError else 'SSO migration failed ('+type(exc).__name__+'); sensitive details suppressed')
