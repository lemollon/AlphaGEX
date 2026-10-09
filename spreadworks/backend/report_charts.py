"""Deterministic dark PNGs from report evidence, never generated illustrations."""
import io, threading, textwrap
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from .report_policy import parse_clock, field_label
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg
from .report_producers import number
LOCK=threading.Lock()
BG='#0B1220'; PANEL='#111827'; TEXT='#E5E7EB'; CYAN='#22D3EE'; GREEN='#34D399'; RED='#F87171'

def chart_png(kind,evidence):
    with LOCK:
        fig=Figure(figsize=(12,6.5),dpi=120,facecolor=BG);FigureCanvasAgg(fig)
        ax=fig.add_subplot(111,facecolor=PANEL,projection='3d' if kind=='surface' else None)
        ax.tick_params(colors=TEXT)
        for s in ax.spines.values():s.set_color('#374151')
        ax.xaxis.label.set_color(TEXT);ax.yaxis.label.set_color(TEXT)
        ax.grid(alpha=.12,color=TEXT);title=kind.replace('_',' ').title();plotted=False
        surfaces=evidence.get('surface') or {};flow=evidence.get('flow') or {}
        generated=parse_clock(evidence.get('generated_at')) or datetime.now(timezone.utc)
        def dated(label,row):
            ts=parse_clock(row.get('source_timestamp') or row.get('chain_timestamp'))
            if not ts:return label+' — update clock unavailable'
            age=(generated-ts).total_seconds()
            return label+(' LIVE NOW' if 0<=age<=90 else ' LAST KNOWN')+' '+ts.astimezone(ZoneInfo('America/Chicago')).strftime('%m/%d %H:%M:%S CT')
        if kind=='smile_term':
            for symbol,row in surfaces.items():
                points=row.get('surface_points') or []
                smile=row.get('smile') or {};expiry=smile.get('expiration') or smile.get('expiry')
                pts=[p for p in points if (not expiry or str(p.get('expiration'))==str(expiry)) and number(p.get('strike')) and number(p.get('iv'))]
                if pts:
                    for right in ('put','call'):
                        subset=sorted([p for p in pts if p.get('right')==right],key=lambda p:p['strike'])
                        if subset:ax.plot([p['strike']/row['spot'] for p in subset],[p['iv']*100 for p in subset],marker='o',markersize=3,label=dated(f'{symbol} {right} {expiry}',row));plotted=True
                elif all(number(smile.get(k)) is not None for k in ('put_strike','atm_strike','call_strike','put_25d_iv','atm_iv','call_25d_iv')) and row.get('spot'):
                    ax.plot([smile[k]/row['spot'] for k in ('put_strike','atm_strike','call_strike')],[smile[k]*100 for k in ('put_25d_iv','atm_iv','call_25d_iv')],marker='o',label=f'{symbol} observed wings');plotted=True
            ax.set_xlabel('Strike / spot');ax.set_ylabel('Observed IV (%)')
        elif kind=='term_structure':
            keys=('iv_0dte','iv_1_5dte','iv_6_20dte','iv_21_365dte')
            for symbol,row in surfaces.items():
                vals=[number(row.get(k)) for k in keys]
                if any(v is not None for v in vals):
                    ax.plot(range(4),[v*100 if v is not None else float('nan') for v in vals],marker='o',label=dated(symbol,row));plotted=True
            ax.set_xticks(range(4),['0DTE','1–5DTE','6–20DTE','21–365DTE'])
            ax.set_ylabel('Observed ATM IV (%)');ax.set_xlabel('Expiry bucket; gaps are not interpolated')
        elif kind=='surface':
            row=next((r for r in surfaces.values() if r.get('surface_points') and r.get('spot')), {})
            points=[p for p in row.get('surface_points') or [] if number(p.get('strike')) and number(p.get('iv')) and number(p.get('dte')) is not None]
            if points:
                ivs=[p['iv']*100 for p in points]
                ax.scatter([p['strike']/row['spot'] for p in points],[p['dte'] for p in points],ivs,c=ivs,cmap='viridis',s=8,alpha=.8);plotted=True
                title=(row.get('symbol') or 'SPY')+' Observed Volatility Surface'
                ax.set_xlabel('Strike / spot',color=TEXT);ax.set_ylabel('Days to expiry',color=TEXT);ax.set_zlabel('IV (%)',color=TEXT)
                ax.tick_params(axis='z',colors=TEXT)
                for axis in (ax.xaxis,ax.yaxis,ax.zaxis):axis.set_pane_color((.067,.094,.153,1))
        elif kind=='flow':
            labels=[];values=[]
            for symbol,row in flow.items():
                for category in ('calls_bought','calls_sold','puts_bought','puts_sold','unclassified'):
                    buckets=(row.get('evidence') or {}).get('buckets') or {}
                    if buckets:
                        labels.append(symbol+' '+category.replace('_',' '));values.append(sum((b.get(category) or {}).get('premium',0) for b in buckets.values()))
            if labels:ax.barh(labels,values,color=CYAN);ax.set_xlabel('Premium ($), captured window only');plotted=True
        elif kind=='gamma_expiry':
            labels=[];values=[]
            for symbol,row in (evidence.get('gamma') or {}).items():
                for bucket,value in (row.get('buckets') or {}).items():
                    v=number(value.get('net_gex_b') if isinstance(value,dict) else value)
                    if v is not None:labels.append(symbol+' '+field_label(bucket));values.append(v)
            if labels:ax.bar(labels,values,color=[GREEN if v>=0 else RED for v in values]);ax.tick_params(axis='x',rotation=30);ax.set_ylabel('Estimated net GEX ($ billions / 1% move)');plotted=True
        elif kind=='sector_credit':
            labels=[];values=[]
            for symbol,row in ((evidence.get('cross_asset') or {}).get('assets') or {}).items():
                p,ref=number(row.get('price')),number(row.get('prev_close'))
                if p and ref:labels.append(symbol);values.append((p/ref-1)*100)
            if labels:ax.bar(labels,values,color=[GREEN if v>=0 else RED for v in values]);ax.set_ylabel('Change vs previous close (%)');plotted=True
        elif kind=='market_map':
            profiles=evidence.get('profiles') or {}
            for symbol,row in surfaces.items():
                low,high=number(row.get('expected_move_low')),number(row.get('expected_move_high'))
                spot=number(row.get('spot'))
                if low and high and spot:
                    y=0 if symbol=='SPY' else 1
                    ax.plot([low,high],[y,y],linewidth=12,alpha=.35,color=CYAN)
                    ax.scatter([spot],[y],color=TEXT,s=80);ax.annotate(f'{dated(symbol,row)}\nEM {low:.2f} | spot {spot:.2f} | EM {high:.2f}',(spot,y),xytext=(0,32),textcoords='offset points',color=TEXT,ha='center');plotted=True
                    profile=profiles.get(symbol) or {}
                    val,vah,poc=(number(profile.get(k)) for k in ('val','vah','poc'))
                    if val is not None and vah is not None:
                        ax.plot([val,vah],[y-.12,y-.12],linewidth=7,color=GREEN,alpha=.5,label=dated(symbol+' observed value area; chop unconfirmed',profile))
                    if poc is not None:ax.scatter([poc],[y-.12],marker='D',color=GREEN,s=40)
                    gamma=(evidence.get('gamma') or {}).get(symbol) or {}
                    for key,label,color in [('gamma_flip','flip','#FBBF24'),('call_wall','call wall',RED),('put_wall','put wall',CYAN)]:
                        level=number(gamma.get(key))
                        if level is not None:
                            ax.plot([level,level],[y-.25,y+.25],color=color,linestyle='--')
                            ax.annotate(f'{label} {level:.2f}',(level,y-.25),xytext=(0,-20),textcoords='offset points',color=color,ha='center',fontsize=8)
            ax.set_yticks([]);ax.set_xlabel('Underlying price; observed expected-move bounds')
        elif kind=='baseline_comparison':
            current=evidence.get('comparison') or {}
            labels=[];values=[]
            for symbol,row in current.items():
                value=number(row.get('price_change_pct'))
                if value is not None:labels.append(symbol);values.append(value)
            if labels:
                positions=list(range(len(labels)));ax.bar([p-.17 for p in positions],values,width=.34,color=CYAN,label='Morning to now')
                previous=evidence.get('prior_comparison') or {}
                prior_vals=[number((previous.get(s) or {}).get('price_change_pct')) for s in labels]
                if any(v is not None for v in prior_vals):ax.bar([p+.17 for p in positions],[v if v is not None else float('nan') for v in prior_vals],width=.34,color=GREEN,label='Prior hour to now')
                ax.set_xticks(positions,labels);ax.set_ylabel('Observed price change (%)');plotted=True
        elif kind=='paper_equity_drawdown':
            hist=(evidence.get('paper') or {}).get('equity_history') or []
            if hist:
                ax.plot(range(len(hist)),[r['equity'] for r in hist],label='Realized paper P&L',color=GREEN)
                ax.fill_between(range(len(hist)),[r['drawdown'] for r in hist],0,color=RED,alpha=.4,label='Drawdown');ax.set_xlabel('Closed paper trades');ax.set_ylabel('$');plotted=True
        elif kind=='event_risk':
            events=evidence.get('events') or []
            if events:
                labels=[textwrap.shorten(r['name'],width=32,placeholder='…')+'\n'+str(r['datetime'])[:16]+(' • estimated' if not r.get('verified') else ' • verified') for r in events[:10]]
                ax.barh(labels,[3 if r.get('impact')=='HIGH' else 2 for r in events[:10]],color='#FBBF24');ax.set_xlabel('Scheduled impact class (not a probability)');plotted=True
        elif kind=='volume_profile':
            for symbol,row in (evidence.get('profiles') or {}).items():
                bins=row.get('bins') or []
                if bins:ax.plot([r['price'] for r in bins],[r['volume'] for r in bins],label=dated(symbol,row));plotted=True
            ax.set_xlabel('Actual traded price bins');ax.set_ylabel('Observed shares')
        if not plotted:
            text_method=ax.text2D if kind=='surface' else ax.text
            text_method(.5,.5,'No verified observations for this panel\nSee Data Integrity for source status',transform=ax.transAxes,ha='center',va='center',color=TEXT,fontsize=17)
        if ax.get_legend_handles_labels()[0]:ax.legend(facecolor=PANEL,labelcolor=TEXT)
        ax.set_title(title,color=TEXT,fontsize=19,pad=20)
        group='surface' if kind in ('market_map','surface','smile_term','term_structure','baseline_comparison') else 'gamma' if kind=='gamma_expiry' else 'profiles' if kind=='volume_profile' else 'flow' if kind=='flow' else None
        clocks=[dated(s,r) for s,r in (evidence.get(group) or {}).items()] if group else [dated(s,r) for s,r in (evidence.get('cross_asset',{}).get('assets') or {}).items()][:3] if kind=='sector_credit' else []
        footer=' | '.join(clocks[:2]) if clocks else 'Source timestamps and coverage in report; event estimates are labeled; paper results are simulations.'
        fig.text(.04,.025,footer,color=TEXT,fontsize=9)
        fig.subplots_adjust(left=.36 if kind=='event_risk' else .19,right=.96,top=.88,bottom=.16)
        out=io.BytesIO();fig.savefig(out,format='png',facecolor=BG);return out.getvalue(),plotted
