# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 7.x     | ✅ Current          |
| < 7.0   | ❌ End of life      |

## Reporting a Vulnerability

If you discover a security vulnerability in Echogent, **please do NOT open a public GitHub issue**.

Instead, please report it privately:

1. **GitHub Security Advisories** (preferred): Use [GitHub's private vulnerability reporting](https://github.com/makiseeee/Echogent/security/advisories/new)
2. **Email**: Reach out to the maintainer directly (see GitHub profile)

### What to include

- Description of the vulnerability
- Steps to reproduce
- Potential impact assessment
- Suggested fix (if any)

### Response Timeline

- **Acknowledgment**: Within 48 hours
- **Initial assessment**: Within 1 week
- **Fix or mitigation**: Best effort, depending on severity

## Security Architecture

Echogent takes security seriously despite being a personal project. Key security measures include:

- **SafeCalculator**: Exponent ≤ 1000 and factorial ≤ 100 thresholds to prevent BigInt DoS
- **WebFetcher SSRF Protection**: Recursive IP resolution with private/loopback address blocking
- **PC Agent Authentication**: Token-based auth for activity reporting endpoint
- **Privacy-first Design**: Window metadata only (zero screenshots), face detection frames never persisted to disk
- **Git-ignored Secrets**: All personal data (`MEMORY.md`, `USER.md`, `.env`, `*.db`) excluded from version control

For more details, see [docs/security.md](docs/security.md).
