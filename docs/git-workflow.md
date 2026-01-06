# 團隊開發流程（非常重要）
[回首頁](../README.md)

## ① 開始開發前，同步最新 main
每次開始寫程式前「一定要做」(確定本地端是最新的)
```bash
git switch main
git pull origin main
```

## ② 隊友開自己的分支開發
建立新分支並切換到所建立的新分支
```bash
git switch -c <分支名稱>
```
推送到 GitHub
```bash
git push -u origin <分支名稱>
```
此時 GitHub 上會多一個分支：
👉 `https://github.com/4team-mma/money/tree/<分支名稱>` <br>

請注意：
- 隊友所有開發都在分支進行
- 不會碰到主線 main
- 不會互相干擾
> ⚠️ 請用自己的名字或功能命名分支 <br>
> 例如：apple、login_feature、apple_v2

## ③ 隊友開發完後，推上自己的分支
先查看自己位於哪個分支
```bash
# 顯示所有本地分支，並以*標示目前所在分支
git branch
```
如果不在自己的分支，請切換到自己的分支
```bash
# 切換分支
git switch <分支名稱>
```
加入所有變更並提交
```bash
git add .
git commit -m "完成 <分支名稱> 分支的功能"
```
推送到 GitHub (遠端)
```bash
git push -u origin <分支名稱>
```

## ④ 在 Github 建立 Pull Request
隊友發 Pull Request（PR）給主控者的審核流程：
1. 打開 GitHub 專案頁面：https://github.com/4team-mma/money
2. 點擊「Compare & pull request」
3. 設定：
   - from：`<分支名稱>`
   - to：`main`
4. 填寫簡單說明
5. 點「Create pull request」(送出 PR)
> 📌 這代表隊友「申請把程式合併到主線(main)」

## ⑤ 主控者會在 Github 做的事：審核後，合併到 main
- 幫隊友看程式碼
- 沒問題就 Merge pull request
- main 分支更新完成

## ⑥ 隊友同步最新 main，繼續下一輪開發
```bash
git switch main
git pull origin main
```

## ⑦ 接著想做新功能就再開一個新的分支，例如：
```bash
git switch -c <分支名稱>
```