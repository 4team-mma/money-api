# 專案結構說明 (Project Structure)
[回首頁](../README.md)<br>
本專案為後端 API 服務，主要採用 Python 開發，並使用 web_app 作為核心邏輯目錄。


    .
    ├── .github/                # GitHub Actions CI/CD 工作流與 Issue 範本
    ├── .vscode/                # VS Code 編輯器設定 (建議插件、Linter 設定)
    ├── docs/                   # 專案相關說明文件
    ├── public/                 # 靜態資源 (不經 Vite 編譯，放 favicon.ico)
    ├── src/                    # 原始碼主目錄
    │   ├── api/                # Axios 接口模組 (與後端溝通邏輯)
    |   |   ├── service.js      # 封裝與後端 API 溝通的核心邏輯
    |   |   ├── index.js        # 把 service + interceptors 組合成統一對外的 API 客戶端
    |   |   └── interceptors.js # 集中管理 Axios 的 請求攔截器與回應攔截器，用來處理錯誤、Token 自動添加等
    │   ├── assets/             # 靜態資源 (由 Vite 編譯，如圖片、 CSS )
    │   ├── components/         # 全域共用 Vue 組件
    │   ├── router/             # Vue Router 路由配置
    │   ├── stores/             # Pinia 狀態管理 (數據中心)
    │   ├── views/              # 頁面組件 (對應路由的視圖頁面)
    │   ├── App.vue             # 根組件
    │   └── main.js             # 前端入口檔案 (掛載外掛、樣式匯入)
    ├── dev.sh                  # Mac 本地開發啟動腳本
    ├── .gitignore              # Git 忽略檔案清單
    ├── index.html              # 單頁應用 HTML 入口
    ├── jsconfig.json           # JavaScript 路徑別名 (@) 設定
    ├── package.json            # 前端套件依賴與腳本
    ├── pnpm-lock.yaml          # pnpm 版本鎖定檔 (確保團隊依賴版本一致)
    ├── README.md               # 專案說明文件
    └── vite.config.js          # Vite 編譯設定
