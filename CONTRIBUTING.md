# Contributing to Echogent

感谢你对 Echogent 的兴趣！以下是参与贡献的指南。

Thank you for your interest in contributing to Echogent! Here's how to get started.

---

## 🌐 Language / 语言

Issues and PRs can be written in **Chinese (中文)** or **English**. Both are welcome.

## 🏗️ Development Setup

### Prerequisites

- Python 3.10+
- Git
- (Optional) Termux + PRoot Ubuntu on Android for full-stack testing

### Clone & Install

```bash
git clone https://github.com/makiseeee/Echogent.git
cd Echogent
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt  # if applicable
```

### Running Tests

```bash
pytest tests/
```

## 📝 Commit Convention

We follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <description>

# Examples:
feat(echo-tools): add voice-to-text service
fix(pc_prober): handle missing window title gracefully
docs(roadmap): update Stage 4 completion status
refactor(obsidian): extract git sync into standalone module
perf(echo-tools): reduce token interceptor overhead
chore(deploy): bump AstrBot startup timeout
```

**Types**: `feat`, `fix`, `docs`, `refactor`, `perf`, `test`, `chore`, `style`, `ci`

**Scopes**: `echo-tools`, `pc_agent`, `desktop_companion`, `obsidian`, `deploy`, `docs`, etc.

## 🔀 Pull Request Process

1. **Fork** the repository and create a feature branch from `main`
2. Make your changes with clear, atomic commits
3. Ensure all tests pass: `pytest tests/`
4. Update documentation if your changes affect user-facing behavior
5. Open a PR using the [PR template](.github/PULL_REQUEST_TEMPLATE.md)
6. Wait for review — the maintainer will respond as soon as possible

## 🏗️ Project Structure

```
astrbot/data/plugins/echo-tools/   # Core plugin (layered architecture)
  ├── core/                        # Config, token interceptor, cron scheduler
  ├── sentries/                    # Battery, PC prober, mind arbiter, Live2D
  ├── services/                    # Model switch, usage report, voice, calculator
  ├── obsidian/                    # Git sync, safe search, task vault
  └── main.py                     # Plugin facade (<150 lines)
echo_pc_agent/                     # Windows system tray agent
desktop_companion/                 # Offline Live2D HUD for MIX 2
scripts/                           # Deployment & utility scripts
docs/                              # Technical documentation
tests/                             # Unit test suite
```

## ⚠️ Important Notes

- **Privacy**: Never commit personal data (`MEMORY.md`, `USER.md`, `wenbo-profile.md`, etc.). These are gitignored for a reason.
- **Lightweight Reloads**: Avoid full service restarts on MIX 2 — the Snapdragon 835 can't handle it gracefully. Use plugin hot-reload whenever possible.
- **Security**: Review [SECURITY.md](SECURITY.md) before making changes to network-facing components.

## 📜 License

By contributing, you agree that your contributions will be licensed under the [Apache License 2.0](LICENSE).
