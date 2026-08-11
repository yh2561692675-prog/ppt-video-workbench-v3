# Cloud collaboration control-plane prototype

This is an isolated, local-only contract prototype for the P2 cloud project.
It uses SQLite in WAL mode and a filesystem object staging directory so the
desktop application remains local-first. It is not wired into `workbench.main`
and must not be deployed as a production service.

Run a local instance with:

```powershell
$env:PYTHONPATH = "apps/api/src;cloud-prototype"
python -c "from app import create_cloud_app; import uvicorn; uvicorn.run(create_cloud_app())"
```

The development-only `X-Actor-ID` header stands in for an OIDC/OAuth2.1 PKCE
identity. Production must replace it with issuer, audience, signature, expiry,
tenant and device checks before enabling any remote endpoint.
