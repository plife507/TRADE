import sys
from pathlib import Path
sys.path.insert(0, 'src')
from src.tools.backtest_play_tools import backtest_run_play_tool

plays = ['S_MX_001_rsi_swing_low','S_MX_002_rsi_swing_high','S_MX_003_ema_trend_align','S_MX_004_macd_trend','S_MX_005_atr_zone','S_MX_006_bbands_zone','S_MX_007_obv_trend','S_MX_008_mfi_zone','S_MX_009_stoch_swing','S_MX_010_adx_swing','S_MX_011_supertrend_swing','S_MX_012_aroon_trend','S_MX_013_kc_zone','S_MX_014_donchian_trend','S_MX_015_squeeze_swing','S_MX_016_vortex_trend','S_MX_017_fisher_zone','S_MX_018_tsi_swing','S_MX_019_kvo_trend','S_MX_020_multi_rsi_macd_swing','S_MX_021_multi_ema_adx_trend','S_MX_022_complex_any_swing','S_MX_023_complex_nested_zone','S_MX_024_complex_multi_trend']
plays_dir = Path('tests/stress/plays/gate_24_mixing/')
results = []
for i, play in enumerate(plays):
    print(f'[{i+1}/24] {play}')
    try:
        result = backtest_run_play_tool(play_id=play, plays_dir=plays_dir, fix_gaps=True, env='live', strict=True)
        status = result.status.upper()
        trades, pnl = 0, 0.0
        if result.data and 'summary' in result.data:
            trades = result.data['summary'].get('trades_count', 0)
            pnl = result.data['summary'].get('net_pnl_usdt', 0.0)
        results.append({'play': play, 'status': status, 'trades': trades, 'pnl': pnl, 'msg': (result.message or '')[:80]})
        print(f'  {status} | {trades} trades | {pnl:.2f}')
    except Exception as e:
        results.append({'play': play, 'status': 'ERROR', 'trades': 0, 'pnl': 0.0, 'msg': str(e)[:80]})
        print(f'  ERROR: {str(e)[:60]}')
print()
print('='*100)
passed = sum(1 for r in results if r['status']=='PASS')
failed = len(results) - passed
zero = [r['play'] for r in results if r['status']=='PASS' and r['trades']==0]
for r in results:
    s = 'OK' if r['status'] == 'PASS' else 'FAIL'
    print(f"{r['play']}: {s} | {r['trades']} | {r['pnl']:.2f}")
print(f'Total={len(plays)} Passed={passed} Failed={failed} ZeroTrades={len(zero)}')
if zero: print('Zero trades:', zero)
fails = [r for r in results if r['status'] \!= 'PASS']
if fails:
    print('Failures:')
    for r in fails: print(f"  {r['play']}: {r['msg']}")
