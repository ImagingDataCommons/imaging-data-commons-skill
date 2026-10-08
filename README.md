# Imaging Data Commons Skill

An AI agent skill for querying and downloading public cancer imaging data from the National Cancer Institute's [Imaging Data Commons (IDC)](https://imaging.datacommons.cancer.gov/). The skill follows the open [Agent Skills](https://agentskills.io/) format and is not specific to any single AI assistant — it works with Claude (claude.ai, Claude Desktop, Claude Code, API) and any other agent that supports the skill format or can load the skill content into its context.

## What This Skill Does

- Find imaging datasets by cancer type, imaging modality (CT, MR, PET, etc.), or anatomy
- Check data licenses and generate proper citations
- Generate download commands, either with the `idc-index` package or as direct transfers from the public S3/GCS buckets
- Provide links to browser-based DICOM viewers for data preview
- Trace data provenance — who contributed each part of a dataset, who de-identified it, and whether IDC converted it to DICOM
- Answer questions about IDC data structure and DICOM metadata

## What You Need

Nothing to install by hand. IDC metadata is reachable with no authentication and no setup at all through the hosted [IDC MCP server](https://api.imaging.datacommons.cancer.gov/mcp) or the equivalent [REST API](https://api.imaging.datacommons.cancer.gov/v3/docs), and the skill picks whichever path is cheapest for the question asked.

Tasks that go past metadata — downloading image files, analysis with pandas, reading pixel data, results past the REST row limits — use the [idc-index](https://github.com/ImagingDataCommons/idc-index) Python package. Installing it is the agent's job rather than a setup step you do up front: the skill works out the right command for the Python interpreter in use and runs it when a task calls for it (a coding agent will ask you to approve the command first). All your environment has to provide is Python 3.10+ and network access, and [USAGE.md](USAGE.md) covers the sandbox settings that allow both.

## Example Questions

Once the skill is loaded, you can ask questions like:

- "Find CT scans of lung cancer in IDC"
- "How do I download all breast MRI data with commercial-use licenses?"
- "Show me the available collections in IDC and their sizes"
- "Generate a citation for the TCGA-BRCA collection"
- "Who de-identified the pathology images in TCGA-BRCA, and did IDC convert them to DICOM?"

## Reporting Issues

If the skill provides incorrect or incomplete answers, please [open an issue](https://github.com/ImagingDataCommons/imaging-data-commons-skill/issues/new/choose) using our issue template.

## Setup Instructions

For coding agents (Claude Code, Codex, Cursor, Gemini CLI, and others), the quickest install is [Skills.sh](https://skills.sh/):

```bash
npx skills add ImagingDataCommons/imaging-data-commons-skill
```

See [USAGE.md](USAGE.md) for every other environment — claude.ai, Claude Desktop, manual installation into an agent's skills directory, the optional IDC MCP server, or loading the skill through an LLM API.

## Versioning

This skill follows [Semantic Versioning](https://semver.org/). Each release records the IDC data version and the `idc-index` version it was verified against in the `SKILL.md` frontmatter.

See [CHANGELOG.md](CHANGELOG.md) for version history and [Releases](https://github.com/ImagingDataCommons/imaging-data-commons-skill/releases) for downloads. For how to stay current with new releases and IDC data versions, see [Keeping the Skill Up to Date](USAGE.md#keeping-the-skill-up-to-date).

If you maintain a skill registry that vendors this skill, see [SYNC.md](SYNC.md) for what the release bundle contains, what upstream holds in CI so your copy needs no local patches, and the steps for one sync.

## Credits

This skill was created and is maintained by [Andrey Fedorov (@fedorov)](https://github.com/fedorov) and the [Imaging Data Commons](https://imaging.datacommons.cancer.gov/) team.

For comprehensive documentation about the skill's capabilities, see [SKILL.md](SKILL.md).

Development of this skill as part of Imaging Data Commons development has been funded in whole or in part with Federal funds from the National Cancer Institute, National Institutes of Health, under Task Order No. HHSN26110071 under Contract No. HHSN261201500003I. 

If you use this skill in your research, please acknowledge IDC by citing the following publication:


> Fedorov, A., Longabaugh, W. J. R., Pot, D., Clunie, D. A., Pieper, S. D., Gibbs, D. L., Bridge, C., Herrmann, M. D., Homeyer, A., Lewis, R., Aerts, H. J. W. L., Krishnaswamy, D., Thiriveedhi, V. K., Ciausu, C., Schacherer, D. P., Bontempi, D., Pihl, T., Wagner, U., Farahani, K., Kim, E. & Kikinis, R. National cancer institute imaging data commons: Toward transparency, reproducibility, and scalability in imaging artificial intelligence. _Radiographics_ 43, (2023). [https://doi.org/10.1148/rg.230180](https://doi.org/10.1148/rg.230180)
  


## License

This skill is licensed under the MIT License. IDC data has individual collection licenses (see skill documentation for details).
