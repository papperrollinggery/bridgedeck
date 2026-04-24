# Open Source Readiness Checklist / 开源准备清单

## Completed / 已完成

- README is bilingual.
- README 已改为中英双语。
- MIT license is included.
- 已加入 MIT 许可证。
- Security policy is included.
- 已加入安全政策。
- Contribution guide is included.
- 已加入贡献说明。
- Changelog is included.
- 已加入变更记录。
- GitHub issue and PR templates are included.
- 已加入 GitHub issue 和 PR 模板。
- Sensitive local handoff notes were moved outside the repository.
- 本地私密 handoff 资料已移出仓库目录。
- `.gitignore` excludes DB files, auth files, logs, virtualenvs, build outputs, and private notes.
- `.gitignore` 已排除 DB、授权文件、日志、虚拟环境、构建产物和私密资料。
- API requires a per-run browser token.
- API 已要求本次启动生成的浏览器令牌。
- Host and Origin checks are enabled.
- 已启用 Host 和 Origin 校验。
- Remote mode is read-only by default.
- 远程模式默认只读。
- Full token reveal is opt-in and disabled in default remote mode.
- 完整 token 显示需要主动操作，默认远程模式禁用。
- JSON writes are atomic.
- JSON 写入已改为原子写。
- Backups go to `~/.cc-switch/bridgedeck-backups/`.
- 备份统一写入 `~/.cc-switch/bridgedeck-backups/`。
- Isolated CLI profiles are restricted to `~/.codex-cli-*`.
- 独立 CLI 配置目录已限制为 `~/.codex-cli-*`。

## Remaining Before Public Release / 公开发布前建议补充

- Sign and notarize the macOS app if distributing to non-technical users.
- 如果面向普通 macOS 用户分发，建议做代码签名和 notarization。
- Publish SHA-256 checksums for DMG releases.
- 发布 DMG 时提供 SHA-256 校验值。
- Add automated tests for API security behavior.
- 为 API 安全行为补自动化测试。
- Split the embedded HTML into a template/static asset if the UI grows further.
- 如果 UI 继续变复杂，拆出 HTML 模板或静态资源。
- Add a compatibility matrix for specific CC Switch versions after more testing.
- 后续测试更多 CC Switch 版本后补兼容性矩阵。
- Decide the final copyright holder in `LICENSE`.
- 确认 `LICENSE` 中最终版权主体。

## Manual Release Check / 手动发布检查

```bash
python3 -m py_compile bridgedeck.py
zsh -n run-bridgedeck.command
zsh -n package-bridgedeck-dmg.command
./package-bridgedeck-dmg.command
shasum -a 256 dist/BridgeDeck.dmg
```

Check that the repository does not contain:

确认仓库不包含：

- `private-notes/`
- `__pycache__/`
- `.env`
- `*.db`
- `*.sqlite*`
- `auth.json`
- `codex_oauth_auth.json`
- `settings.json`
- private screenshots or logs
- 私人截图或日志
