# web_app/services/stock_api_service.py
import httpx
import asyncio
class StockApiService:
    @staticmethod
    async def get_market_snapshot(tickers: list[str]) -> dict:
        """
        雙軌官方查詢：同時抓取 TWSE 的「本益比/殖利率」與「收盤價」。
        查不到殖利率的 ETF 或上櫃股票，才動用 Yahoo Finance 備援。
        """
        results = {}
        
        # 1. 定義 TWSE 兩支官方 API
        url_ratios = "https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL" # 比例表 (無價格)
        url_prices = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL" # 價格表 (含ETF，無比例)
        
        twse_ratios_data = []
        twse_prices_data = []
        
        try:
            async with httpx.AsyncClient() as client:
                # 🌟 核心技巧：平行發送請求，時間減半！
                resp_ratios, resp_prices = await asyncio.gather(
                    client.get(url_ratios, timeout=5.0),
                    client.get(url_prices, timeout=5.0),
                    return_exceptions=True
                )
                
                if isinstance(resp_ratios, httpx.Response) and resp_ratios.status_code == 200:
                    twse_ratios_data = resp_ratios.json()
                if isinstance(resp_prices, httpx.Response) and resp_prices.status_code == 200:
                    twse_prices_data = resp_prices.json()
        except Exception as e:
            print(f"[Stock API] TWSE 查詢失敗: {e}")

        # 建立 TWSE 快速查找字典
        ratios_dict = {item.get("Code"): item for item in twse_ratios_data if isinstance(item, dict)}
        prices_dict = {item.get("Code"): item for item in twse_prices_data if isinstance(item, dict)}

        missing_tickers = []
        
        for ticker in tickers:
            # 只要在價格表或比例表有資料，就代表 TWSE 有這檔標的
            if ticker in ratios_dict or ticker in prices_dict:
                ratio_info = ratios_dict.get(ticker, {})
                price_info = prices_dict.get(ticker, {})
                
                # 組合出完整的官方資料
                results[ticker] = {
                    "股票名稱": price_info.get("Name") or ratio_info.get("Name"),
                    "最新股價": price_info.get("ClosingPrice", "無價格資料"),
                    "殖利率": f"{ratio_info.get('DividendYield')}%" if ratio_info.get('DividendYield') else None,
                    "本益比 (PE)": ratio_info.get("PEratio", "無資料 (可能為ETF)"),
                    "股價淨值比 (PB)": ratio_info.get("PBratio", "無資料 (可能為ETF)"),
                    "資料來源": "TWSE 台灣證交所 OpenAPI (官方)",
                    "價格口徑": "官方盤後收盤價"
                }
                
                # 🛡️ 如果是 ETF (官方有價格，但官方不提供殖利率)，把它加入備援名單去跟 Yahoo 要殖利率
                if not results[ticker]["殖利率"]:
                    results[ticker]["殖利率"] = "官方無資料"
                    missing_tickers.append(ticker)
            else:
                # 完全不在 TWSE 裡面 (可能是上櫃股票或美股)
                missing_tickers.append(ticker)

        # 2. 啟動 Yahoo 備援：補齊 ETF 的殖利率，或查詢完全查不到的上櫃/美股
        if missing_tickers:
            yahoo_results = await StockApiService._get_yahoo_fallback(missing_tickers)
            
            for t, y_data in yahoo_results.items():
                if t in results and "TWSE" in results[t]["資料來源"]:
                    # 情境 A：TWSE 有價格，只缺殖利率 (例如 0056) -> 縫合資料
                    results[t]["殖利率"] = y_data.get("殖利率", "查無備援殖利率")
                    results[t]["資料來源"] += " + Yahoo(補齊殖利率)"
                else:
                    # 情境 B：TWSE 完全沒有 (例如 00713 上櫃) -> 整包用 Yahoo 的
                    results[t] = y_data

        return results

    @staticmethod
    async def _get_yahoo_fallback(tickers: list[str]) -> dict:
        """非官方 Yahoo 備援查詢，自動處理 .TW (上市) 與 .TWO (上櫃)"""
        results = {}
        query_symbols = []
        
        for t in tickers:
            if t.isdigit():
                # 為了涵蓋上市與上櫃，把 .TW 和 .TWO 都組進去查，總有一個會中
                query_symbols.extend([f"{t}.TW", f"{t}.TWO"])
            else:
                query_symbols.append(t)

        url = "https://query1.finance.yahoo.com/v7/finance/quote"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/91.0.4472.124 Safari/537.36"
        }
        
        try:
            async with httpx.AsyncClient() as client:
                # 💡 Codex 建議：使用 params 來讓 httpx 安全編碼 URL
                resp = await client.get(url, params={"symbols": ",".join(query_symbols)}, headers=headers, timeout=5.0)
                if resp.status_code == 200:
                    data = resp.json()
                    result_list = data.get("quoteResponse", {}).get("result", [])
                    
                    for stock in result_list:
                        symbol = stock.get("symbol", "")
                        # 拔掉後綴還原代號
                        base_ticker = symbol.replace(".TW", "").replace(".TWO", "")
                        
                        raw_yield = stock.get("trailingAnnualDividendYield")
                        yield_percent = f"{round(raw_yield * 100, 2)}%" if raw_yield else "無配息資料"
                        
                        results[base_ticker] = {
                            "股票名稱": stock.get("shortName", base_ticker),
                            "最新股價": stock.get("regularMarketPrice", "查無股價"),
                            "殖利率": yield_percent,
                            "本益比 (PE)": stock.get("trailingPE", "無資料 (ETF)"),
                            "資料來源": "Yahoo Finance (Unofficial Fallback)",
                            "殖利率口徑": "Trailing Annual Yield (近一年股息 / 現價估算)"
                        }
        except Exception as e:
            print(f"[Stock API] Yahoo 備援查詢失敗: {e}")

        # 標示完全查不到的標的
        for t in tickers:
            if t not in results:
                results[t] = {"錯誤": "TWSE 與 Yahoo 皆查無此標的資訊，請確認代號是否正確。"}
                
        return results