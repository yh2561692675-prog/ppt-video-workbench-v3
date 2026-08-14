UPDATE jobs
SET core_contracts_json = replace(
    core_contracts_json,
    '7c63aab737d6fe9281ce83cd8fec0e2ddf52f2148d51938f6be4f80ac55f5488',
    'd5c1c5a0116fd4da38825bad535c075bfc476a4694b276d7ff5ff3e9cbfda1e6'
)
WHERE core_contracts_json LIKE '%7c63aab737d6fe9281ce83cd8fec0e2ddf52f2148d51938f6be4f80ac55f5488%';
