# Benchmark source and license notes

## Real puzzle pilot

- **Author / archive:** Steve Weyer, via CommuniCrossings and the Ashland.news crossword archive.
- **Archive page:** https://communicrossings.com/crosswords-weyer-2025
- **Puzzle-file URLs:** enumerated per puzzle in [`ashland-2025.json`](ashland-2025.json).
- **Stated license:** Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International (CC BY-NC-SA 4.0), as described by the source archive.
- **License text:** https://creativecommons.org/licenses/by-nc-sa/4.0/
- **Handling:** raw `.puz` files and converted clues/answers are downloaded only to ignored `data/real_benchmark/`. They are not in this repository, source ZIP, or Git history. The local importer writes `ATTRIBUTION.txt` and refuses to run without `--noncommercial-use`.

The source's noncommercial/share-alike restrictions may not fit every future portfolio or commercial use. Check the original source and license before sharing any puzzle text or derived corpus; ask the rights holder if the intended use is unclear.

## Candidate public-domain source investigated

Project Gutenberg contains early crossword books, including https://www.gutenberg.org/ebooks/68267 and its subject catalog at https://www.gutenberg.org/ebooks/subject/37838. The digitized books did not provide a convenient machine-readable gold answer grid for this project, so they are not used in the pilot manifest.

## Token Factory API

- API overview: https://docs.tokenfactory.nebius.com/api-reference/introduction
- Model list endpoint docs: https://docs.tokenfactory.nebius.com/api-reference/models/list-models
- API OpenAPI document: https://api.tokenfactory.nebius.com/openapi.json
- Documented base URL: `https://api.tokenfactory.nebius.com/v1`

The project does not store API keys, and this note does not assert that any hosted-model experiment has been run.
