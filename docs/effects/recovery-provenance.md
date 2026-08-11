# Recovery provenance

- Recovered from the existing `PPTVideoWorkbench_Task26_RunAll_v3.zip` / `PPTVideoWorkbench_Task26_OneClick_Repair_v2.zip` files when present.
- Reused the 30 non-blank single-page PPTX files from the uploaded sample archive; the blank `鏂伴珮涓€瑙勫垝_娣辫壊绉戞妧椋巁7.pptx` was not included.
- Restored contracts from the previously frozen Task 21鈥?5 state: 30-page manifest, Ground Truth, per-page visual review, release-candidate manifest, strict release models, and isolated Windows acceptance tests.
- No production database, user workspace, API key, access token, or secret is included.
- `release-candidate-manifest.json` is a blocked baseline because this Linux recovery environment does not contain the Windows installer. It must not be read as a passing Windows RC.
