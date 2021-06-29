import time
from slack_sdk import WebClient
from apscheduler.schedulers.background import BackgroundScheduler
import os
from slack_sdk.web.async_client import AsyncWebClient
from slack_sdk.errors import SlackApiError
import requests
from flask import abort, Flask, json, jsonify, request
from pykrx import stock
from bs4 import BeautifulSoup
from datetime import datetime

os.environ['TZ']= 'Asia/Seoul'

app = Flask(__name__)

slack_channel = "#주식거래"
slack_token = ""
"""
pip install APScheduler
pip install slack_sdk
pip install aiohttp
pip install requests
pip install pykrx
pip install flask
"""
client = WebClient(token=slack_token)

stocks = {}

def get_code(stock_code):
    url = "https://finance.naver.com/item/main.nhn?code=" + stock_code
    result = requests.get(url)
    bs_obj = BeautifulSoup(result.content, "html.parser")
    return bs_obj

def get_price(stock_code):
    bs_obj = get_code(stock_code)
    no_today = bs_obj.find("p", {"class":"no_today"})
    blind = no_today.find("span", {"class":"blind"})
    now_price = blind.text
    return now_price

def stock_load():
    """
    저장된 파일에서 지정된 데이터를 읽어 옵니다.
    """
    global stocks
    try:

        with open('stock_alert.json', encoding='UTF-8') as f:
            stocks = json.load(f)
        send_to_slack(slack_channel, '주식 데이터를 로드 완료 했습니다.')

    except Exception as e:
        send_to_slack(slack_channel, 'stock_alert.json 파일을 확인해주세요.')

    return

def stock_save():
    with open('stock_alert.json','w', encoding='UTF-8') as f:
        f.write(json.dumps(stocks, ensure_ascii = False))
    return    

def slack_send(msg):
    client.chat_postMessage(channel=slack_channel, text=msg)
    

def is_working():
   
    today = datetime.today()
    
    if today.hour < 9:
        return False
    if today.hour > 15:
        return False
    if today.hour == 15 and today.minute > 30:
        return False
    if today.weekday() == 5 or today.weekday() == 6:
        return False
    
    return True

def check_stock_price_list():

    if is_working() == False:
        return
    
    text = ""
    for key in stocks.keys():
        price = get_price(key)
        goal = format(stocks[key]['price'], ",")
        text += f"종목 : {stocks[key]['name']}[{key}] 목표가: {goal} 현재가: {price}\n"

    slack_send(text)
    return

def check_stock_price():
    """
    주기적으로 현 시세를 조회 후 
    가격이 일치 할때 
    """
    if is_working() == False:
        return
    
    for key in stocks.keys():
        s = stocks[key]
        goal_price = s['price']
        cur_price = int(get_price(key).replace(',',''))
        
        goal = format(goal_price, ",")
        if s['cond'] == "up" and goal_price < cur_price:
            slack_send(f"종목 : {s['name']}[{key}] 목표가 {goal}원 을 넘어섰습니다.")
            
        if s['cond'] == "dn" and goal_price > cur_price:
            slack_send(f"종목 : {s['name']}[{key}] 목표가 {goal}원 미만으로 떨어졌습니다.")
            
        if goal_price == cur_price:
            slack_send(f"종목 : {s['name']}[{key}] 목표가 {goal}원 에 도달 하였습니다.")

    return

def send_to_slack(channel, text):
    try:
        response = client.chat_postMessage(channel=channel, text=text)
        assert response["message"]["text"] == text
    except SlackApiError as e:
        assert e.response["ok"] is False
        assert e.response["error"]
        raise 

@app.route('/del', methods=[ 'POST'])
def stock_del():
    in_params = request.form['text']
    if in_params.startswith('*') and in_params[-1] == "*":
        in_params = in_params[1:-1]

    try:
        del stocks[in_params]
    except KeyError:
        pass
    
    stock_save()


@app.route('/add', methods=[ 'POST'])
def stock_add():

    in_params = request.form['text']
    if in_params.startswith('*') and in_params[-1] == "*":
        in_params = in_params[1:-1]

    params = in_params.split(' ')

    if len(params) < 2:
        return jsonify(
        response_type='in_channel',
        text=f"입력된 항목이 올바르지 않습니다. \n/add [종목코드] [금액] [상/하]", )

    stock_code = params[0]
    stock_price = params[1]
    stock_cond = "eq"

    msg = ''
    if len(params) == 3:
        if params[2].lower() == "상":
            stock_cond = "up"
        if params[2].lower() == "하":
            stock_cond = "dn"

    stock_name = stock.get_market_ticker_name(stock_code)
    
    if stock_cond == "up":
        msg = f'종목 {stock_name}[{stock_code}] {stock_price} 원 초과시 알람이 등록되었습니다.'
    elif stock_cond == "dn":
        msg = f'종목 {stock_name}[{stock_code}] {stock_price} 원 미만시 알람이 등록되었습니다.'
    else:
        msg = f'종목 {stock_name}[{stock_code}] {stock_price} 원 알람이 등록되었습니다.'
    
    stocks[stock_code] = {'name': stock_name,
                          'price': int(stock_price), 'cond': stock_cond}

    print(f" 종목코드: {stock_code}, 종목명: {stock_name}")
    if len(stock_name) == 0:
        return jsonify(
        response_type='in_channel',
        text=f"존재 하지 않는 종목입니다. ", )
        stocks[stock_code] = {"price": int(
            stock_price), 'name': stock_name, 'cond': stock_cond}

    stock_save()
    try:
        return jsonify(
        response_type='in_channel',
        text=msg, )
    except SlackApiError as e:
        return jsonify(
        response_type='in_channel',
        text=f"Failed due to {e.response['error']}", )


@app.route('/list', methods=['POST'])
def stock_list():

    txt = ""

    for key in stocks.keys():
        goal = format(stocks[key]['price'], ",")
        
        if stocks[key]['cond'] == "up":
            cond = "초과시"
        elif stocks[key]['cond'] == "dn":
            cond = "미만시"
        else:
            cond = "도달시"
            
        txt += f"종목: {stocks[key]['name']}[{key}] {goal}원 {cond}\n"

    try:

        return jsonify(
        response_type='in_channel',
        text=txt, )
    except SlackApiError as e:
        return jsonify(
        response_type='in_channel',
        text=f"Failed due to {e.response['error']}", )

if __name__ == "__main__":
    print("변동성 돌파 전략 주식매매를 시작합니다.")

    stock_load()

    scheduler = BackgroundScheduler()
    scheduler.add_job(check_stock_price, 'interval', seconds=10 )
    scheduler.add_job(check_stock_price_list, 'interval', minutes=10)
    scheduler.start()

    app.run(host='0.0.0.0', port=3000)

