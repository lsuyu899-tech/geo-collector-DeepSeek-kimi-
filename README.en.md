# GEO Collector Standalone (Release README)

A standalone, GitHub-ready project for collecting cited sources from AI responses:

- Batch prompts from CSV/TXT
- Supports Kimi / Doubao (ARK) / DeepSeek
- Extracts source links and tags source channels
- Generates channel summary rankings automatically
- Provides both GUI and CLI workflows

## Project Structure

- `collector.py`: core collector (CLI)
- `app.py`: GUI wrapper
- `run_app.bat`: GUI launcher
- `run_cli.bat`: interactive CLI launcher
- `questions.csv`: sample input
- `LICENSE`: MIT license
- `.gitignore`: recommended ignore rules

## Requirements

- Windows
- Python 3.6+
- No third-party dependencies (standard library only)

## Quick Start (GUI, Recommended)

1. Double-click `run_app.bat`
2. Configure:
   - input file (`questions.csv`)
   - output file (`results.csv`)
   - API keys (MOONSHOT / ARK / DEEPSEEK)
   - models and workers
3. Click `开始运行`

## Quick Start (CLI)

Double-click `run_cli.bat` and follow prompts.

## Input Format

Supported:

1. `questions.txt`: one question per line
2. `questions.csv`: default question column is `question`

Example:

```csv
question
What is the best way to learn futures trading?
Why do I keep losing in futures trading?
Where should beginners start with futures?
```

## Output Files

After each run:

1. Main output file (e.g., `results.csv`)
2. Summary file: `<output>_渠道统计汇总.csv`

Main output includes:

- answers from each platform
- source links and channel tags
- status per platform (ok/skip/error)
- elapsed time and timestamps

## Security Notes

1. Do not commit real API keys.
2. `settings.json` is not storing API keys and is ignored by default.
3. Rotate keys immediately if exposed.

## Troubleshooting

1. Kimi temperature errors: collector auto-adapts when API enforces a fixed value.
2. Doubao `ToolNotOpen`: enable ARK web-search plugin first.
3. DeepSeek source behavior can differ from app/web due to API capability differences.

## License

[MIT License](./LICENSE)
