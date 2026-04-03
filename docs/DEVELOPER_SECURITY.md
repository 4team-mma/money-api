# 🧠 AI 喵喵專案：開發者key保護手冊

為了保護專案的 `HF_TOKEN` 與 `API_KEY` 不被意外上傳到 GitHub，本專案啟動了 **Git Pre-commit 守門員機制**。

## 🚀 隊友第一次加入專案時
請在克隆 (Clone) 專案後，於 `money-api` 目錄執行以下動作：

1. **同步開發環境**：
   使用 `uv` 統一安裝所有依賴（包含開發工具）：
   ```bash
   uv sync
   或者 uv add pre-commit

2. 碰到被機器人攔截，如何更新「白名單」(Baseline):
-  新增了模型設定或特定亂碼，導致 pre-commit 檢查失敗但你確定該程式碼安全時
```bash
# 執行此指令更新免死金牌清單 (Windows 建議指令)
uv run python -c "import subprocess; out = subprocess.check_output(['detect-secrets', 'scan']); open('.secrets.baseline', 'wb').write(out)"

# Mac
uv run detect-secrets scan > .secrets.baseline

```
更新後，請執行 git add .secrets.baseline 再重新 commit 即可。

移除:
- rm .secrets.baseline