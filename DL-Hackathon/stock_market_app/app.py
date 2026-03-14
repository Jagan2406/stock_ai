import yfinance as yf
import pandas as pd
import numpy as np
from flask import Flask, render_template, request, jsonify, session
from sklearn.linear_model import LinearRegression
import plotly.graph_objs as go
import plotly.utils
import json
from datetime import datetime
import traceback
import locale

app = Flask(__name__)
app.secret_key = 'super_secret_key_for_session'

# Initial balance in INR (e.g., 10 Lakhs)
INITIAL_BALANCE = 1000000.0

def get_usd_inr_rate():
    try:
        # Fetch live exchange rate
        ticker = yf.Ticker("INR=X")
        data = ticker.history(period="1d")
        if not data.empty:
            rate = data['Close'].iloc[-1]
            return rate
    except Exception as e:
        print(f"Error fetching exchange rate: {e}")
    return 84.0  # Fallback approximate rate

def format_inr(number):
    """
    Format number to Indian Currency format: ₹1,23,456.78
    """
    try:
        n = float(number)
        s, *d = str(f"{n:.2f}").partition(".")
        r = ",".join([s[x-2:x] for x in range(-3, -len(s), -2)][::-1] + [s[-3:]])
        formatted = "".join([r] + d)
        return f"₹{formatted}"
    except:
        return f"₹{number}"

def get_stock_data(ticker_symbol):
    print(f"Fetching data for: {ticker_symbol}")
    try:
        stock = yf.Ticker(ticker_symbol)
        hist = stock.history(period="3mo")
        
        if hist.empty:
            print(f"WARNING: No data found for {ticker_symbol}")
            return None, None
            
        # Try to get currency info
        currency = 'USD' # Default
        try:
            # Fast info fetch
            if 'currency' in stock.info:
                currency = stock.info['currency']
            elif ticker_symbol.endswith('.NS') or ticker_symbol.endswith('.BO'):
                currency = 'INR'
        except:
            pass
            
        return hist, currency
    except Exception as e:
        print(f"ERROR: Exception fetching data for {ticker_symbol}: {e}")
        traceback.print_exc()
        return None, None

def train_predict_model(df):
    try:
        X = df[['DateOrdinal']]
        y = df['Close']
        
        model = LinearRegression()
        model.fit(X, y)
        
        # Calculate Confidence Score (R^2 Score)
        confidence = model.score(X, y)
        
        last_ordinal = df['DateOrdinal'].iloc[-1]
        next_day_ordinal = [[last_ordinal + 1]]
        
        predicted_price = model.predict(next_day_ordinal)[0]
        
        return predicted_price, model, confidence
    except Exception as e:
        print(f"ERROR: Prediction failed: {e}")
        traceback.print_exc()
        return None, None, 0.0

def generate_ai_insight(current, predicted, confidence):
    diff_percent = ((predicted - current) / current) * 100
    strength = "Low"
    if confidence > 0.7: strength = "High"
    elif confidence > 0.4: strength = "Medium"
    
    direction = "positive" if predicted > current else "negative"
    
    insight = f"AI model detects a {strength} confidence {direction} trend. "
    if abs(diff_percent) > 1.0:
        insight += f"Significant movement of {diff_percent:.2f}% expected."
    else:
        insight += "Market expected to remain relatively stable."
        
    return insight

@app.route('/', methods=['GET', 'POST'])
def index():
    if 'balance' not in session:
        session['balance'] = INITIAL_BALANCE
        session['holdings'] = {}
        session['history'] = []
    
    context = {}
    context['cash_balance'] = format_inr(session['balance'])
    
    portfolio_value = session['balance']
    
    # Calculate initial portfolio value from session
    for t, data in session.get('holdings', {}).items():
        # Use stored avg_price as fallback for value calculation if we don't fetch new data
        portfolio_value += data['shares'] * data['avg_price']

    context['portfolio_value'] = format_inr(portfolio_value)
    
    if request.method == 'POST':
        ticker = request.form.get('ticker', '').upper().strip()
        context['ticker'] = ticker
        
        if ticker:
            df, currency = get_stock_data(ticker)
            
            if df is not None and not df.empty:
                # Currency Conversion Logic
                exchange_rate = 1.0
                currency_label = currency
                
                if currency == 'USD':
                    exchange_rate = get_usd_inr_rate()
                    print(f"Converting USD to INR with rate: {exchange_rate}")
                    # Convert DataFrame columns
                    for col in ['Open', 'High', 'Low', 'Close']:
                        df[col] = df[col] * exchange_rate
                    currency_label = 'INR'
                else:
                    print(f"Stock is already in {currency}, no conversion needed.")

                df = df.reset_index()
                date_col = 'Date' if 'Date' in df.columns else 'index'
                df['DateOrdinal'] = df.index
                
                current_price = df['Close'].iloc[-1]
                
                # Train model and get confidence score
                predicted_price, model, confidence = train_predict_model(df)
                
                if predicted_price is not None:
                    trend = "UP" if predicted_price > current_price else "DOWN"
                    difference = predicted_price - current_price
                    recommendation = "HOLD"
                    if predicted_price > current_price * 1.005:
                        recommendation = "BUY"
                    elif predicted_price < current_price * 0.995:
                        recommendation = "SELL"
                        
                    ai_insight = generate_ai_insight(current_price, predicted_price, confidence)
                    
                    # Simulation Logic
                    action_taken = "NONE"
                    shares_to_trade = 0
                    
                    if recommendation == "BUY":
                        invest_amount = session['balance'] * 0.5
                        if invest_amount > current_price:
                            shares_to_trade = int(invest_amount // current_price)
                            cost = shares_to_trade * current_price
                            session['balance'] -= cost
                            
                            if ticker not in session['holdings']:
                                session['holdings'][ticker] = {'shares': 0, 'avg_price': 0.0}
                            
                            old_info = session['holdings'][ticker]
                            total_cost = (old_info['shares'] * old_info['avg_price']) + cost
                            new_shares = old_info['shares'] + shares_to_trade
                            
                            session['holdings'][ticker]['shares'] = new_shares
                            # Store avg_price in INR
                            session['holdings'][ticker]['avg_price'] = total_cost / new_shares
                            
                            action_taken = f"BOUGHT {shares_to_trade}"
                            session['history'].append({
                                'date': datetime.now().strftime("%Y-%m-%d %H:%M"),
                                'ticker': ticker,
                                'action': 'BUY',
                                'price': current_price,
                                'shares': shares_to_trade
                            })
                            
                    elif recommendation == "SELL":
                        if ticker in session['holdings'] and session['holdings'][ticker]['shares'] > 0:
                            shares_to_trade = session['holdings'][ticker]['shares']
                            revenue = shares_to_trade * current_price
                            session['balance'] += revenue
                            
                            del session['holdings'][ticker]
                            
                            action_taken = f"SOLD {shares_to_trade}"
                            session['history'].append({
                                'date': datetime.now().strftime("%Y-%m-%d %H:%M"),
                                'ticker': ticker,
                                'action': 'SELL',
                                'price': current_price,
                                'shares': shares_to_trade
                            })
                    
                    session.modified = True
                    
                    # Recalculate Portfolio Value with updated holdings and LIVE price for current ticker
                    portfolio_value = session['balance']
                    holdings_list = []
                    
                    for t, data in session['holdings'].items():
                        # If t is the current ticker, use current_price (already in INR)
                        # If t is another ticker, we use the stored avg_price (which is in INR) 
                        # Ideally we should fetch live prices for all, but for speed we use stored avg or current if matched
                        price_to_use = current_price if t == ticker else data['avg_price']
                        
                        val = data['shares'] * price_to_use
                        portfolio_value += val
                        
                        holdings_list.append({
                            'ticker': t,
                            'shares': data['shares'],
                            'avg_price': format_inr(data['avg_price']),
                            'current_value': format_inr(val)
                        })
                    
                    # Graph
                    fig = go.Figure()
                    fig.add_trace(go.Candlestick(
                        x=df[date_col],
                        open=df['Open'],
                        high=df['High'],
                        low=df['Low'],
                        close=df['Close'],
                        name=f'Market Price analysis({currency_label})'
                    ))
                    
                    last_date = df[date_col].iloc[-1]
                    next_date = last_date + pd.Timedelta(days=1)
                    
                    fig.add_trace(go.Scatter(
                        x=[last_date, next_date],
                        y=[current_price, predicted_price],
                        mode='lines+markers',
                        name='AI Prediction',
                        line=dict(color='blue', width=2, dash='dash')
                    ))
                    
                    fig.update_layout(
                        title=f'{ticker} Analysis ({currency_label})',
                        yaxis_title=f'Price ({currency_label})',
                        xaxis_title='Date',
                        template='plotly_white',
                        height=500
                    )
                    graphJSON = json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)
                    
                    context.update({
                        'current_price': format_inr(current_price),
                        'predicted_price': format_inr(predicted_price),
                        'difference': format_inr(difference),
                        'trend': trend,
                        'recommendation': recommendation,
                        'confidence_score': f"{confidence*100:.1f}%",
                        'ai_insight': ai_insight,
                        'action_taken': action_taken,
                        'graphJSON': graphJSON,
                        'portfolio_value': format_inr(portfolio_value),
                        'cash_balance': format_inr(session['balance']),
                        'holdings': holdings_list,
                        'history': [{
                            'date': h['date'],
                            'ticker': h['ticker'],
                            'action': h['action'],
                            'price': format_inr(h['price']),
                            'shares': h['shares']
                        } for h in session['history'][-5:]]
                    })
                else:
                    context['error'] = "Stock value is randomly changing could not predict"
            else:
                context['error'] = f"Could not fetch data for {ticker}."

    return render_template('index.html', **context)

@app.route('/reset', methods=['POST'])
def reset_portfolio():
    session['balance'] = INITIAL_BALANCE
    session['holdings'] = {}
    session['history'] = []
    return jsonify({'status': 'success'})

@app.route('/calculate_forecast', methods=['POST'])
def calculate_forecast():
    try:
        ticker = request.form.get('ticker')
        amount = float(request.form.get('amount'))
        date_str = request.form.get('date')
        
        target_date = datetime.strptime(date_str, '%Y-%m-%d')
        today = datetime.now()
        
        if target_date <= today:
            return jsonify({'error': 'Please select a future date.'})
            
        df, currency = get_stock_data(ticker)
        if df is None:
            return jsonify({'error': 'Stock data not found.'})
            
        # Currency check (same as index)
        exchange_rate = 1.0
        if currency == 'USD':
            exchange_rate = get_usd_inr_rate()
            for col in ['Open', 'High', 'Low', 'Close']:
                df[col] = df[col] * exchange_rate
        
        df = df.reset_index()
        df['DateOrdinal'] = df.index
        
        predicted_price, model, confidence = train_predict_model(df)
        if predicted_price is None:
             return jsonify({'error': 'Prediction failed.'})
             
        # Project for specific date
        # We need to estimate how many trading days are between now and target_date
        # Simple approximation: difference in days * (5/7) ? 
        # Or better: extend the ordinal logic. 
        # The model is trained on 'index' (0, 1, 2...). 
        # Last index corresponds to df.iloc[-1]['Date']
        
        last_date_in_data = df.iloc[-1]['Date'].replace(tzinfo=None) # Ensure naive
        delta_days = (target_date - last_date_in_data).days
        
        if delta_days <= 0:
             # Should not happen if target_date > today and data is recent
             delta_days = 1
        
        # Approximate trading days (skip weekends roughly)
        # exact trading days is hard without a calendar, but we can approximate:
        # linear regression on time doesn't care about gaps if we used Ordinal Date (datetime.toordinal()).
        # But here we used index `0, 1, 2`. This assumes equidistant steps. 
        # If we want to consistency, we should project index.
        # Average rows per day? 
        
        # Better approach for this Hackathon:
        # Re-train model using actual Time Ordinals if we want date accuracy?
        # OR: Just assume 1 index unit = 1 day (including weekends/holidays gap? No data gaps exist).
        # Data fetched is '3mo'. 
        # Let's use the Ratio: (Target Date - Start Date) / (Last Date - Start Date) mapped to indices?
        
        # Let's switch to using Real Date Ordinals for the Projection calculation to be robust for "Future Date"
        # Re-train locally for this request
        df['RealDateOrdinal'] = pd.to_datetime(df['Date']).map(datetime.toordinal)
        
        X_new = df[['RealDateOrdinal']]
        y_new = df['Close']
        model_new = LinearRegression()
        model_new.fit(X_new, y_new)
        
        target_ordinal = target_date.toordinal()
        future_price = model_new.predict([[target_ordinal]])[0]
        
        # Current Price
        current_price = df['Close'].iloc[-1]
        
        # Calculation
        num_shares = amount / current_price
        future_val = num_shares * future_price
        profit_loss = future_val - amount
        pct_change = (profit_loss / amount) * 100
        
        return jsonify({
            'predicted_price': format_inr(future_price),
            'future_value': format_inr(future_val),
            'profit_loss': format_inr(profit_loss),
            'percentage': f"{pct_change:.2f}",
            'is_profit': bool(profit_loss >= 0)
        })
        
    except Exception as e:
        print(e)
        traceback.print_exc()
        return jsonify({'error': str(e)})

@app.route('/trending')
def trending():
    # Predefined list of major stocks
    tickers = [
        {'ticker': 'RELIANCE.NS', 'name': 'Reliance Ind.'},
        {'ticker': 'TCS.NS', 'name': 'TCS'},
        {'ticker': 'HDFCBANK.NS', 'name': 'HDFC Bank'},
        {'ticker': 'INFY.NS', 'name': 'Infosys'},
        {'ticker': 'SBIN.NS', 'name': 'SBI'},
        {'ticker': 'TATAMOTORS.NS', 'name': 'Tata Motors'},
        {'ticker': 'AAPL', 'name': 'Apple Inc.'},
        {'ticker': 'AMZN', 'name': 'Amazon'},
        {'ticker': 'TSLA', 'name': 'Tesla'},
        {'ticker': 'NVDA', 'name': 'NVIDIA'}
    ]
    
    buy_list = []
    sell_list = []
    
    usd_inr = get_usd_inr_rate()
    
    for t in tickers:
        try:
            stock = yf.Ticker(t['ticker'])
            # Get fast info first if possible, else history
            # .fast_info is faster
            price = 0.0
            change_pct = 0.0
            
            # Attempt to use history for consistency with graph data logic
            # specifically to get accurate today vs yesterday
            hist = stock.history(period="2d")
            
            if len(hist) >= 1:
                current_close = hist['Close'].iloc[-1]
                
                # Determine prev close
                prev_close = current_close # Default
                if len(hist) >= 2:
                     prev_close = hist['Close'].iloc[-2]
                
                # Currency conversion if USD
                # Heuristic: US stocks don't end in .NS
                is_usd = not t['ticker'].endswith('.NS')
                
                if is_usd:
                    current_close *= usd_inr
                    prev_close *= usd_inr
                
                # Calculate change
                if prev_close > 0:
                    change_pct = ((current_close - prev_close) / prev_close) * 100
                
                stock_data = {
                    'name': t['name'],
                    'ticker': t['ticker'],
                    'price': format_inr(current_close),
                    'change': f"{change_pct:.2f}"
                }
                
                # Categorize
                # If Price Risen (> 0) -> Time to Sell
                # If Price Dropped (< 0) -> Time to Buy
                if change_pct >= 0:
                    sell_list.append(stock_data)
                else:
                    buy_list.append(stock_data)
                    
        except Exception as e:
            print(f"Error fetching trending data for {t['ticker']}: {e}")
            continue
            
    return render_template('trending.html', buy_list=buy_list, sell_list=sell_list)

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
