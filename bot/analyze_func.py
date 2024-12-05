from dotenv import load_dotenv
import os
import pandas as pd
import requests
from datetime import datetime
import config


load_dotenv(".env", override=True)
BINGX_API_URL = config.bingx_api_url
DEV_GRAPHQL_API = config.dev_graphql_api


def connect_copin_api(query):
    """Kết nối vào API của copin để lấy thông tin"""
    url = DEV_GRAPHQL_API

    payload = {
        "query": query,
    }
    try:
        response = requests.post(url, json=payload)
        data = response.json()
        df = pd.DataFrame(data["data"])

        df.rename(columns={df.columns[0]: "copin"}, inplace=True)
        df_result = pd.DataFrame(df["copin"]["data"])

        return df_result
    except Exception as e:
        # Hiển thị thông báo lỗi
        result = "GraphQL bị lỗi"

        return result


def query_strategy_day_trading():
    query = f"""
    query {{
        searchPositionStatistic(
            index: "copin.position_statistics"
            body: {{
            filter: {{
                and: [

                {{ field: "type", match: "D30" }}
                {{ field: "avgDuration"
                    gte : "3600"
                    lte : "7200"
                }}
                ]
            }}
            sorts: [{{ field: "realisedPnl", direction: "desc" }}]
            paging: {{ size: 500, from: 0 }}
            }}
        ) {{
            data {{  
                account
                protocol
                
                avgDuration     
                totalTrade
                realisedPnl
                realisedAvgRoi
            }}
            meta {{
                total
                limit
                offset
                totalPages
            }}
        }}
    }}
    """
    result = connect_copin_api(query)
    return result


def query_strategy_scalping():
    query = f"""
    query {{
        searchPositionStatistic(
            index: "copin.position_statistics"
            body: {{
            filter: {{
                and: [

                {{ field: "type", match: "D30" }}
                {{ field: "avgDuration"
                    
                    lte : "3600"
                }}
                ]
            }}
            sorts: [{{ field: "realisedPnl", direction: "desc" }}]
            paging: {{ size: 500, from: 0 }}
            }}
        ) {{
            data {{  
                account
                protocol
                
                avgDuration     
                totalTrade
                realisedPnl
                realisedAvgRoi
            }}
            meta {{
                total
                limit
                offset
                totalPages
            }}
        }}
    }}
    """
    result = connect_copin_api(query)
    return result


def query_position_statistics(account, type):
    """Lấy position statistics của trader"""
    query = f"""
    query {{
        searchPositionStatistic(
            index: "copin.position_statistics"
            body: {{
            filter: {{
                and: [
                {{ field: "account", match: "{account}" }}

                {{ field: "type", match: "{type}" }}
                ]
            }}
            sorts: [{{ field: "realisedPnl", direction: "desc" }}]
            paging: {{ size: 12, from: 0 }}
            }}
        ) {{
            data {{  
                
                protocol
                
                avgDuration     
                totalTrade
                winRate
                avgLeverage  
                realisedPnl
                realisedAvgRoi
                realisedMaxRoi
                realisedMaxDrawdown
                realisedMaxDrawdownPnl
                realisedGainLossRatio
            }}
            meta {{
                total
                limit
                offset
                totalPages
            }}
        }}
    }}
    """
    result = connect_copin_api(query)
    return result


def query_position(account):
    """Trả lại list 20 vị thế của trader với những chỉ số cần thiết"""
    query = f"""
        query {{
            searchTopOpeningPosition(
                index: "copin.positions"
                protocols: [
                    "GMX"
                    "GMX_V2"
                    "KWENTA"
                    "POLYNOMIAL"
                    "GNS"
                    "GNS_POLY"
                    "GNS_BASE"
                    "MUX_ARB"
                    "AVANTIS_BASE"
                    "CYBERDEX"
                    "DEXTORO"
                    "VELA_ARB"
                    "EQUATION_ARB"
                    "HMX_ARB"
                    "LEVEL_ARB"
                    "LEVEL_BNB"
                    "APOLLOX_BNB"
                    "KILOEX_OPBNB"
                    "COPIN"
                    "KTX_MANTLE"
                    "LOGX_BLAST"
                    "LOGX_MODE"
                    "MYX_ARB"
                    "PERENNIAL_ARB"
                    "ROLLIE_SCROLL"
                    "SYNTHETIX_V3"
                    "TIGRIS_ARB"
                    "YFX_ARB"
                    "MUMMY_FANTOM"
                ]
                body: {{
                    filter: {{
                        and: [
                        {{ field: "status", match: "CLOSE" }}
                        {{
                            field: "account", match: "{account}"
                        }}
                        ]
                    }}
                    sorts: [{{ field: "closeBlockTime", direction: "desc" }}]
                    paging: {{ size: 20, from: 0 }}
                }}
            ) {{
                data {{
                    
                    openBlockTime
                    closeBlockTime
                    pair
                    durationInSecond
                    leverage                    
                    isWin
                    isLong
                    averagePrice
                    realisedRoi
                    realisedPnl
                    
                    


                }}
                meta {{
                    total
                    limit
                    offset
                    totalPages
                }}
            }}
        }}
    """

    result = connect_copin_api(query)
    return result


def analyze_real_position(account):
    """Tính toán những chỉ số của trader qua 20 vị thế gần nhất"""
    recent_position = query_position(account)
    if recent_position.empty | isinstance(recent_position, str):
        return (
            "Không tìm thấy trader này hoặc trader này chưa thực hiện bất kì vị thế nào"
        )
    else:
        recent_stats = pd.DataFrame({"account": [account]})

        recent_stats = recent_stats.assign(
            pnl=None,
            winRate=None,
            profitFactor=None,
            maxDrawdown=None,
            avgRoi=None,
            avgDuration=None,
            avgLossRoi=None,
        )
        exists_loss = (recent_position["isWin"] == False).any()
        if exists_loss:
            loss_ROI = recent_position[recent_position["isWin"] == False]["realisedRoi"]
            recent_stats["avgLossRoi"] = loss_ROI.mean()
            recent_stats["maxDrawdown"] = recent_position["realisedPnl"].min()
        recent_stats["pnl"] = recent_position["realisedPnl"].sum()
        recent_stats["avgRoi"] = recent_position["realisedRoi"].mean()
        recent_stats["avgDuration"] = recent_position["durationInSecond"].mean()
        recent_stats["winRate"] = recent_position["isWin"].sum() / len(recent_position)
        total_win_pnl = recent_position[recent_position["isWin"] == True][
            "realisedPnl"
        ].sum()
        total_loss_pnl = recent_position[recent_position["isWin"] == False][
            "realisedPnl"
        ].sum()
        if total_loss_pnl != 0:
            recent_stats["profitFactor"] = total_win_pnl / abs(total_loss_pnl)
        else:
            recent_stats["profitFactor"] = total_win_pnl

        return recent_stats


def query_position(account):
    """Trả lại list 20 vị thế của trader với những chỉ số cần thiết"""
    query = f"""
        query {{
            searchTopOpeningPosition(
                index: "copin.positions"
                protocols: [
                    "GMX"
                    "GMX_V2"
                    "KWENTA"
                    "POLYNOMIAL"
                    "GNS"
                    "GNS_POLY"
                    "GNS_BASE"
                    "MUX_ARB"
                    "AVANTIS_BASE"
                    "CYBERDEX"
                    "DEXTORO"
                    "VELA_ARB"
                    "EQUATION_ARB"
                    "HMX_ARB"
                    "LEVEL_ARB"
                    "LEVEL_BNB"
                    "APOLLOX_BNB"
                    "KILOEX_OPBNB"
                    "COPIN"
                    "KTX_MANTLE"
                    "LOGX_BLAST"
                    "LOGX_MODE"
                    "MYX_ARB"
                    "PERENNIAL_ARB"
                    "ROLLIE_SCROLL"
                    "SYNTHETIX_V3"
                    "TIGRIS_ARB"
                    "YFX_ARB"
                    "MUMMY_FANTOM"
                ]
                body: {{
                    filter: {{
                        and: [
                        {{ field: "status", match: "CLOSE" }}
                        {{
                            field: "account", match: "{account}"
                        }}
                        {{ field: "orderCount", match: "2" }}
                        ]
                    }}
                    sorts: [{{ field: "closeBlockTime", direction: "desc" }}]
                    paging: {{ size: 20, from: 0 }}
                }}
            ) {{
                data {{
                    
                    openBlockTime
                    closeBlockTime
                    pair
                    durationInSecond
                    leverage                    
                    isWin
                    isLong
                    realisedRoi
                    collateral
                    size
                    realisedPnl
                    


                }}
                meta {{
                    total
                    limit
                    offset
                    totalPages
                }}
            }}
        }}
    """

    result = connect_copin_api(query)
    return result


def convert_timestamp(time):
    """Chuyển isodate sang timestamp"""
    iso_date = time
    timestamp = int(datetime.fromisoformat(iso_date).timestamp() * 1000)

    return timestamp


def check_interval(duration):
    """Chọn interval phù hợp để khi connect API dữ liệu không quá limit"""
    if (duration / 60) <= 1000:
        return "1m"
    elif (duration / 300) <= 1000:
        return "5m"
    elif (duration / 1800) <= 1000:
        return "30m"
    elif (duration / 3600) <= 1000:
        return "1h"
    elif (duration / 14400) <= 1000:
        return "4h"
    else:
        return "1d"


def connect_price_API_BINGX(pair, interval, open_time, close_time, limit: int = 1000):
    APIURL = BINGX_API_URL
    pair_mapping = {
        "RNDR-USDT": "RENDER-USDT",
        "PEPE-USDT": "1000PEPE-USDT",
        "BONK-USDT": "1000BONK-USDT",
        "1000DOGS-USDT": "DOGS-USDT",
        "1000FLOKI-USDT": "FLOKI-USDT",
        "1000SHIB-USDT": "SHIB-USDT",
        # Thêm các cặp khác nếu cần
    }

    pair = pair_mapping.get(pair, pair)

    paramsMap = {
        "symbol": pair,
        "interval": interval,
        "limit": limit,
        "startTime": open_time,
        "endTime": close_time,
    }

    # Thêm timestamp vào paramsMap
    # paramsMap["timestamp"] = str(int(time.time() * 1000))

    # URL của API endpoint

    # Gửi yêu cầu GET với paramsMap
    response = requests.get(APIURL, params=paramsMap)

    data = response.json()
    df = pd.DataFrame(data["data"])
    df_final = df.sort_index(ascending=False).reset_index(drop=True)
    df_final.drop(["volume"], axis=1, inplace=True)

    df_final = df_final.rename(
        columns={
            "time": "timestamp",
            "open": "open_price",
            "close": "close_price",
            "high": "high_price",
            "low": "low_price",
        }
    )
    return df_final


def connect_price_API_BITGET(pair, interval, open_time, close_time, limit: int = 1000):
    APIURL = BITGET_API_URL
    pair_mapping = {
        "RNDRUSDT": "RENDERUSDT",
        "BONKUSDT": "1000BONKUSDT",
        "1000DOGSUSDT": "DOGSUSDT",
        "1000FLOKIUSDT": "FLOKIUSDT",
        "1000PEPEUSDT": "PEPEUSDT",
        "1000SHIBUSDT": "SHIBUSDT",
        # Thêm các cặp khác nếu cần
    }
    pair = pair.replace("-", "")
    pair = pair_mapping.get(pair, pair)
    interval_mapping = {
        "1h": "1H",
        "4h": "4H",
        "1d": "1D",
        # Thêm các cặp khác nếu cần
    }
    interval = interval_mapping.get(interval, interval)
    paramsMap = {
        "symbol": pair,
        "productType": "USDT-FUTURES",
        "granularity": interval,
        "limit": limit,
        "startTime": open_time,
        "endTime": close_time,
    }

    # Gửi yêu cầu GET với paramsMap
    response = requests.get(APIURL, params=paramsMap)

    data = response.json()
    df = pd.DataFrame(
        data["data"],
        columns=[
            "timestamp",
            "open_price",
            "high_price",
            "low_price",
            "close_price",
            "volume_coins",
            "volume_currency",
        ],
    )
    df_final = df[["timestamp", "open_price", "close_price", "high_price", "low_price"]]
    return df_final


def interval_to_second(interval):
    if interval == "1m":
        return 60
    elif interval == "5m":
        return 300
    elif interval == "30m":
        return 1800
    elif interval == "1h":
        return 3600
    elif interval == "4h":
        return 14400
    elif interval == "1d":
        return 86400


def check_price_crypto(protocol, pair, interval, open_time, close_time):
    if protocol == "BINGX":
        price_crypto = connect_price_API_BINGX(pair, interval, open_time, close_time)

    elif protocol == "BITGET":
        price_crypto = connect_price_API_BITGET(pair, interval, open_time, close_time)

    price_crypto["open_price"] = pd.to_numeric(
        price_crypto["open_price"], errors="coerce"
    )
    price_crypto["close_price"] = pd.to_numeric(
        price_crypto["close_price"], errors="coerce"
    )
    price_crypto["high_price"] = pd.to_numeric(
        price_crypto["high_price"], errors="coerce"
    )
    price_crypto["low_price"] = pd.to_numeric(
        price_crypto["low_price"], errors="coerce"
    )
    return price_crypto


def analyze_position(
    pair,
    interval,
    open_time,
    close_time,
    isLong,
    isWin,
    leverage,
    protocol,
):
    try:
        price_crypto = check_price_crypto(
            protocol, pair, interval, open_time, close_time
        )

        buy_price = price_crypto["open_price"][0]

        analyze_position = pd.DataFrame({"timestamp": price_crypto["timestamp"]})

        roi_close = ((price_crypto["close_price"] / buy_price) - 1) * leverage * 100
        roi_high = ((price_crypto["high_price"] / buy_price) - 1) * leverage * 100
        roi_low = ((price_crypto["low_price"] / buy_price) - 1) * leverage * 100
        if isLong == True:
            analyze_position["roi_close"] = roi_close
            analyze_position["roi_high"] = roi_high
            analyze_position["roi_low"] = roi_low
        else:
            analyze_position["roi_close"] = -roi_close
            analyze_position["roi_high"] = -roi_low
            analyze_position["roi_low"] = -roi_high

        analyze_position["BH"] = analyze_position["roi_close"] < 0

        max_streak = (analyze_position["BH"] != analyze_position["BH"].shift()).cumsum()
        longest_lose_streak = (
            analyze_position[analyze_position["BH"]].groupby(max_streak).size().max()
        )

        roi_final = analyze_position["roi_close"].iloc[-1]

        min_roi = analyze_position["roi_low"].min()
        max_roi = analyze_position["roi_high"].max()

        exist_BH = (analyze_position["BH"] == True).any()

        if exist_BH:
            duration_second_interval = interval_to_second(interval)

            total_lose_duration = (
                analyze_position["BH"].sum() * duration_second_interval
            )
            total_lose_streak_duration = longest_lose_streak * duration_second_interval
            ##LossTime
            loss_time = (total_lose_duration * 1000 / (close_time - open_time)) * 100

            ###ConsecutiveLossTime
            consecutive_loss_time = (
                total_lose_streak_duration * 1000 / (close_time - open_time)
            ) * 100
            ##LossHandling

            if isWin == True:
                loss_Handling = min_roi
            else:
                loss_Handling = None

        else:
            loss_time = None
            consecutive_loss_time = None
            loss_Handling = None

        if isWin == True:
            ##TPEfficiency
            TPEfficiency = roi_final / max_roi * 100

        else:
            TPEfficiency = None

        # TP_Late
        exist_tp = (analyze_position["roi_close"] > 0).any()
        if exist_tp:
            index_max_roi = analyze_position["roi_high"].idxmax()
            timestamp_max = int(analyze_position.loc[index_max_roi, "timestamp"])

            if timestamp_max < close_time:
                TP_Late = True

            else:
                TP_Late = False

        else:
            TP_Late = None
    except Exception as e:
        print(e)
        print(pair)
        (
            roi_final,
            loss_Handling,
            TPEfficiency,
            TP_Late,
        ) = (None, None, None, None)

    return (roi_final, loss_Handling, TPEfficiency, min_roi, max_roi)


def analyze_trader(account, protocol):
    """Hâm phân tích trader"""

    trader = pd.DataFrame({"account": [account]})

    trader = trader.assign(
        avgRoiFinal=None,
        avgLossROI=None,
        avgTPEfficiency=None,
        avgLossHandling=None,
        winRate=None,
        profitFactor=None,
        avgLeverage=None,
        winStreak=None,
        loseStreak=None,
    )

    list_position = query_position(account)

    if list_position.empty | isinstance(list_position, str):
        print(f"account ko co data : {account}")
        return "Không tìm thấy dữ liệu về trader này", "Không có vị thế nào cả"

    else:
        list_position = list_position.assign(
            RoiFinal=None,
            TPEfficiency=None,
            TPLate=None,
            LossHandling=None,
            MinRoi=None,
            MaxRoi=None,
        )
        for index_1, row_1 in list_position.iterrows():
            open_time = convert_timestamp(list_position.at[index_1, "openBlockTime"])
            close_time = convert_timestamp(list_position.at[index_1, "closeBlockTime"])

            duration_position = list_position.at[index_1, "durationInSecond"]
            pair = list_position.at[index_1, "pair"]
            pair = pair.replace('"', "")
            leverage = list_position.at[index_1, "leverage"]

            interval = check_interval(duration_position)
            isLong = row_1["isLong"]
            isWin = row_1["isWin"]

            try:

                (roi_final, loss_Handling, TPEfficiency, min_roi, max_roi) = (
                    analyze_position(
                        pair,
                        interval,
                        open_time,
                        close_time,
                        isLong,
                        isWin,
                        leverage,
                        protocol,
                    )
                )
                list_position.at[index_1, "RoiFinal"] = roi_final
                list_position.at[index_1, "LossHandling"] = loss_Handling
                list_position.at[index_1, "TPEfficiency"] = TPEfficiency
                list_position.at[index_1, "MinRoi"] = min_roi
                list_position.at[index_1, "MaxRoi"] = max_roi

            except Exception as e:
                print("Đã xảy ra lỗi:", e)
                print(
                    f"'{pair}','{interval}',{open_time},{close_time},{isLong},{isWin},{leverage}"
                )
                pass

        ##AverageRoiFinal
        trader["avgRoiFinal"] = list_position["RoiFinal"].mean()

        ##AverageLossROI

        exists_loss = (list_position["isWin"] == False).any()
        if exists_loss:
            loss_ROI = list_position[list_position["isWin"] == False]["RoiFinal"]
            loss_roi = loss_ROI.mean()
            trader["avgLossROI"] = loss_roi

        ##avgTPEfficiency
        trader["avgTPEfficiency"] = list_position["TPEfficiency"].mean()

        ##avgLossHandling
        lossHandling = list_position[list_position["LossHandling"] != 0]["LossHandling"]
        avgLossHandling = lossHandling.mean()
        trader["avgLossHandling"] = avgLossHandling
        ##winRate
        trader["winRate"] = list_position["isWin"].sum() / len(list_position)
        # profitFactor
        total_profit = list_position[list_position["realisedPnl"] > 0][
            "realisedPnl"
        ].sum()
        total_loss = abs(  #
            list_position[list_position["realisedPnl"] < 0]["realisedPnl"].sum()
        )
        if total_loss > 0:
            profit_factor = total_profit / total_loss
        else:
            profit_factor = total_profit
        trader["profitFactor"] = profit_factor
        # avgLeverage
        trader["avgLeverage"] = list_position["leverage"].mean()
        # winStreak, loseStreak
        last_3_positions = list_position["isWin"].iloc[:3]

        winStreak = last_3_positions.all()
        loseStreak = (last_3_positions == False).all()

        trader["winStreak"] = winStreak
        trader["loseStreak"] = loseStreak
        # take_profit

        take_profit = list_position["MaxRoi"].mean()
        trader["TakeProfit"] = take_profit

        list_position_2 = list_position.drop(
            ["openBlockTime", "closeBlockTime"], axis=1
        )
        # stop_loss
        if avgLossHandling > loss_roi:
            stop_loss = trader["avgLossHandling"]
        else:
            stop_loss = trader["avgLossROI"]
        trader["stopLoss"] = stop_loss
        # Reverse copy
        reverse_copy = False
        if loseStreak | trader["winRate"] <= 0.5:
            reverse_copy = True
            trader["TakeProfit"] = -stop_loss
            trader["stopLoss"] = -take_profit

        result = []
        result.append(
            reverse_copy,
            trader["avgLeverage"],
            trader["TakeProfit"],
            trader["stopLoss"],
        )

    return result
