UPDATE jobs
SET core_contracts_json = replace(
    core_contracts_json,
    '7c63aab737d6fe9281ce83cd8fec0e2ddf52f2148d51938f6be4f80ac55f5488',
    'de55cc1090e49b0ab4d7fb6375b4509cb878d5888e8bef54fd00407a34fbebf6'
)
WHERE core_contracts_json LIKE '%7c63aab737d6fe9281ce83cd8fec0e2ddf52f2148d51938f6be4f80ac55f5488%';
