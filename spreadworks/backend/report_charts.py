"""Deterministic dark PNGs from report evidence, never generated illustrations.

Phone-first (UX review 2026-10-16): charts are drawn at ~800px native width (they display at
~320px on a phone, so the old 1440px canvas shrank text to ~3px), every font is sized for that
downscale, values sit on the bars, each symbol gets its own panel/x-range, legends live outside
the plot, and titles state what the chart shows. Every number drawn comes from `evidence`.
"""
import io, math, threading, textwrap
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from .report_policy import parse_clock, field_label
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.patches import Patch
from matplotlib.ticker import FuncFormatter
from .report_producers import number
from .report_contract import LIVE_MAX_AGE_SECONDS
LOCK=threading.Lock()
BG='#0B1220'; PANEL='#111827'; TEXT='#E5E7EB'; SUB='#CBD5E1'; CYAN='#22D3EE'; GREEN='#34D399'; RED='#F87171'; VIOLET='#A78BFA'; AMBER='#FBBF24'
SYM_COLOR={'SPY':'#56B4E9','QQQ':'#E69F00'}
CALL_COLOR={'SPY':'#D55E00','QQQ':'#009E73'}
PALETTE=['#56B4E9','#E69F00','#CC79A7','#009E73','#F0E442','#D55E00']
CALLOUT_BBOX=dict(boxstyle='round,pad=0.35',fc=PANEL,ec='#374151',alpha=.92)
W=8.0; DPI=100
FS_TICK=11; FS_LABEL=12; FS_VALUE=11; FS_LEGEND=10

def money(v):
    a=abs(v);s='-' if v<0 else ''
    return s+('$%.1fM'%(a/1e6) if a>=1e6 else '$%.0fK'%(a/1e3) if a>=1e3 else '$%.0f'%a)

def compact(v):
    a=abs(v);s='-' if v<0 else ''
    return s+('%.1fM'%(a/1e6) if a>=1e6 else '%.0fK'%(a/1e3) if a>=1e3 else '%.0f'%a)

def style(ax):
    ax.set_facecolor(PANEL);ax.tick_params(colors=TEXT,labelsize=FS_TICK)
    for s in ax.spines.values():s.set_color('#374151')
    ax.xaxis.label.set_color(TEXT);ax.yaxis.label.set_color(TEXT)
    ax.xaxis.label.set_size(FS_LABEL);ax.yaxis.label.set_size(FS_LABEL)
    ax.grid(alpha=.15,color=TEXT);ax.set_prop_cycle(color=PALETTE)

def mk(n=1,heights=None):
    fig=Figure(figsize=(W,5.8),dpi=DPI,facecolor=BG);FigureCanvasAgg(fig)
    axs=[fig.add_subplot(n,1,i+1) for i in range(n)]
    for ax in axs:style(ax)
    return fig,axs

def finish(fig,axs,title,sub,legend,footer,ph=3.2,extra=0.0,left=.15,right=.96,xl=.8):
    """Lay out header/legend/footer in inches so text never overlaps the plot, then size the canvas."""
    lines=textwrap.wrap(title,50) or [title]
    head=.12+.3*len(lines)+(.06+.2*(sub.count('\n')+1) if sub else 0)
    seen=set();h=[];l=[]
    for ax in axs:
        for hh,ll in zip(*ax.get_legend_handles_labels()):
            if ll and not ll.startswith('_') and ll not in seen:seen.add(ll);h.append(hh);l.append(ll)
    for hh,ll in legend or []:
        if ll not in seen:seen.add(ll);h.append(hh);l.append(ll)
    ncol=2 if any(len(x)>22 for x in l) else 3
    leg_in=(.12+.27*math.ceil(len(l)/ncol)) if l else 0
    flines=textwrap.wrap(footer,88) or ['']
    foot_in=.12+.18*len(flines)
    gap=(extra+.55) if len(axs)>1 else 0
    topgap=extra+(.3 if len(axs)>1 else 0)  # room for the first panel's own title/level strip
    H=head+.12+topgap+len(axs)*ph+gap*(len(axs)-1)+xl+leg_in+foot_in
    fig.set_size_inches(W,H)
    fig.text(.04,1-.12/H,'\n'.join(lines),color=TEXT,fontsize=15,fontweight='bold',va='top',linespacing=1.15)
    if sub:fig.text(.04,1-(.12+.3*len(lines)+.06)/H,sub,color=SUB,fontsize=10,va='top',linespacing=1.4)
    if l:fig.legend(h,l,loc='lower center',bbox_to_anchor=(.5,foot_in/H),ncol=ncol,fontsize=FS_LEGEND,facecolor=PANEL,labelcolor=TEXT,edgecolor='#374151',framealpha=.95)
    fig.text(.04,.08/H,'\n'.join(flines),color=SUB,fontsize=10,va='bottom',linespacing=1.3)
    fig.subplots_adjust(left=left,right=right,top=1-(head+.12+topgap)/H,bottom=(foot_in+leg_in+xl)/H,hspace=gap/ph if len(axs)>1 else None)

def level_list(evidence,symbol):
    """Spot / flip / call wall / put wall for `symbol`, only the ones present in evidence."""
    spot=number(((evidence.get('surface') or {}).get(symbol) or {}).get('spot'))
    gamma=(evidence.get('gamma') or {}).get(symbol) or {}
    out=[]
    if spot is not None:out.append(('spot',spot,TEXT))
    for key,label,color in (('gamma_flip','flip',AMBER),('call_wall','call wall',RED),('put_wall','put wall',VIOLET)):
        v=number(gamma.get(key))
        if v is not None:out.append((label,v,color))
    return out

def levels_text(evidence,symbols):
    rows=[]
    for s in symbols:
        lv=level_list(evidence,s)
        if lv:rows.append(s+'  '+' · '.join(f'{label} {v:.2f}' for label,v,_ in lv))
    return '\n'.join(rows[:2])

def draw_levels(ax,levels,scale=1.0,prefix=''):
    """Dashed verticals on a price axis, labelled in a staggered strip ABOVE the axes so labels never hit data."""
    lo,hi=ax.get_xlim()
    for rank,(label,v,color) in enumerate(sorted(levels,key=lambda t:t[1])):
        x=v/scale
        ax.axvline(x,color=color,linestyle='--',linewidth=1.2,alpha=.9)
        frac=(x-lo)/((hi-lo) or 1)
        ha='right' if frac>.8 else 'left' if frac<.2 else 'center'
        ax.annotate(f'{prefix}{label} {v:.2f}',(x,1.0),xycoords=('data','axes fraction'),xytext=(0,4+14*rank),textcoords='offset points',color=color,ha=ha,va='bottom',fontsize=10,fontweight='bold')
    return .19*len(levels)

def bar_values(ax,bars,texts,horizontal=False):
    ax.bar_label(bars,labels=texts,padding=3,color=TEXT,fontsize=FS_VALUE,fontweight='bold')

def chart_png(kind,evidence):
    with LOCK:
        fig,axs=mk();ax=axs[0]
        title=kind.replace('_',' ').title();sub='';plotted=False;extra=0.0;ph=3.2;left=.15;legend=[]
        surfaces=evidence.get('surface') or {};flow=evidence.get('flow') or {}
        generated=parse_clock(evidence.get('generated_at')) or datetime.now(timezone.utc)
        def stamp(label,row):
            ts=parse_clock(row.get('source_timestamp') or row.get('chain_timestamp'))
            if not ts:return label+': update time unavailable'
            local=ts.astimezone(ZoneInfo('America/Chicago'))
            if 0<=(generated-ts).total_seconds()<=LIVE_MAX_AGE_SECONDS:return f'{label} live, {local.strftime("%I:%M %p").lstrip("0")} CT'
            return f'{label} last known, {local.strftime("%m/%d")} {local.strftime("%I:%M %p").lstrip("0")} CT'
        if kind=='smile_term':
            shown=[];fallback=0
            for symbol,row in surfaces.items():
                points=row.get('surface_points') or []
                smile=row.get('smile') or {};expiry=smile.get('expiration') or smile.get('expiry')
                pts=[p for p in points if (not expiry or str(p.get('expiration'))==str(expiry)) and number(p.get('strike')) and number(p.get('iv'))]
                if pts and row.get('spot'):
                    for right in ('put','call'):
                        subset=sorted([p for p in pts if p.get('right')==right],key=lambda p:p['strike'])
                        if subset:
                            ax.plot([p['strike']/row['spot'] for p in subset],[p['iv']*100 for p in subset],marker='o',markersize=4,linewidth=2,
                                    color=(SYM_COLOR if right=='put' else CALL_COLOR).get(symbol,PALETTE[len(shown)%len(PALETTE)]),linestyle='-' if right=='put' else '--',
                                    label=f'{symbol} {right}s'+(f' (exp {expiry})' if expiry else ''));plotted=True
                            if symbol not in shown:shown.append(symbol)
                elif all(number(smile.get(k)) is not None for k in ('put_strike','atm_strike','call_strike','put_25d_iv','atm_iv','call_25d_iv')) and row.get('spot'):
                    ax.plot([smile[k]/row['spot'] for k in ('put_strike','atm_strike','call_strike')],[smile[k]*100 for k in ('put_25d_iv','atm_iv','call_25d_iv')],marker='o',markersize=5,linewidth=2,label=f'{symbol} observed wings');plotted=True
                    if symbol not in shown:shown.append(symbol)
            ax.set_xlabel('Strike / spot (1.00 = spot)');ax.set_ylabel('Observed IV (%)')
            if plotted:
                title='Implied volatility by strike: '+' and '.join(shown)
                lv=level_list(evidence,shown[0]);scale=number(surfaces[shown[0]].get('spot'))
                if lv and scale:extra=draw_levels(ax,lv,scale,prefix='' if len(shown)==1 else shown[0]+' ')
        elif kind=='term_structure':
            keys=('iv_0dte','iv_1_5dte','iv_6_20dte','iv_21_365dte');head=None
            for symbol,row in surfaces.items():
                vals=[number(row.get(k)) for k in keys]
                if any(v is not None for v in vals):
                    ax.plot(range(4),[v*100 if v is not None else float('nan') for v in vals],marker='o',markersize=6,linewidth=2.5,label=symbol)
                    for i,v in enumerate(vals):
                        if v is not None:ax.annotate(f'{v*100:.1f}',(i,v*100),xytext=(0,8),textcoords='offset points',ha='center',fontsize=10,color=TEXT)
                    plotted=True
                    if head is None and vals[0] is not None and vals[3] is not None:head=(symbol,vals[0],vals[3])
            ax.set_xticks(range(4),['0DTE','1–5DTE','6–20DTE','21+DTE']);ax.margins(y=.15)
            ax.set_ylabel('Observed ATM IV (%)');ax.set_xlabel('Expiry bucket; gaps are not interpolated')
            if head:title=f'{head[0]} front-end IV is {"above" if head[1]>head[2] else "below"} longer-dated IV' if head[1]!=head[2] else f'{head[0]} front-end IV equals longer-dated IV'
            elif plotted:title='Implied volatility by expiry bucket'
        elif kind=='surface':
            symbol,row=next(((s,r) for s,r in surfaces.items() if r.get('surface_points') and r.get('spot')),(None,{}))
            points=[p for p in row.get('surface_points') or [] if number(p.get('strike')) and number(p.get('iv')) and number(p.get('dte')) is not None]
            spot=number(row.get('spot'))
            if points and spot:
                otm=[p for p in points if p.get('right') not in ('put','call') or (p['right']=='put' and p['strike']<=spot) or (p['right']=='call' and p['strike']>=spot)]
                use=otm or points
                dtes=sorted({p['dte'] for p in use})[:5]
                for i,d in enumerate(dtes):
                    sub_pts=sorted([p for p in use if p['dte']==d],key=lambda p:p['strike'])
                    ax.plot([p['strike'] for p in sub_pts],[p['iv']*100 for p in sub_pts],marker='o',markersize=3.5,linewidth=2,color=PALETTE[i%len(PALETTE)],label=f'{d:g} DTE')
                ivs=[p['iv']*100 for p in use if p['dte'] in dtes];lo,hi=min(ivs),max(ivs);pad=((hi-lo) or hi or 1)*.1
                ax.set_ylim(lo-pad,hi+pad)
                ax.set_xlabel('Strike ($)'+('; out-of-the-money options' if any(p.get('right') in ('put','call') for p in use) else ''));ax.set_ylabel('Observed IV (%)')
                title=f'{(row.get("symbol") or symbol)} implied volatility by strike, nearest expiries'
                lv=level_list(evidence,symbol)
                if lv:extra=draw_levels(ax,lv)
                plotted=True
        elif kind=='flow':
            labels=[];values=[];colors=[];hatches=[];unclassified=0.0;used=[]
            for symbol,row in flow.items():
                buckets=(row.get('evidence') or {}).get('buckets') or {}
                if not buckets:continue
                for category in ('calls_bought','calls_sold','puts_bought','puts_sold','unclassified'):
                    total=sum(number((b.get(category) or {}).get('premium')) or 0 for b in buckets.values())
                    if category=='unclassified':unclassified+=total;continue
                    labels.append(symbol+' '+category.replace('_',' '));values.append(total)
                    colors.append(SYM_COLOR.get(symbol,PALETTE[len(used)%len(PALETTE)]));hatches.append('' if category.endswith('bought') else '//')
                    if symbol not in used:used.append(symbol)
            if labels:
                bars=ax.barh(labels,values,color=colors,edgecolor=BG)
                for b,hh in zip(bars,hatches):b.set_hatch(hh)
                ax.invert_yaxis();bar_values(ax,bars,[money(v) for v in values]);ax.margins(x=.2)
                ax.xaxis.set_major_formatter(FuncFormatter(lambda v,_:money(v)));ax.set_xlabel('Premium, captured window only')
                legend=[(Patch(fc='#9CA3AF',ec=BG),'Solid: bought'),(Patch(fc='#9CA3AF',ec=BG,hatch='//'),'Hatched: sold')]+[(Patch(fc=SYM_COLOR.get(s,PALETTE[i%len(PALETTE)])),s) for i,s in enumerate(used)]
                top=max(zip(labels,values),key=lambda t:abs(t[1]))
                title=f'Largest options flow: {top[0]} at {money(top[1])}'
                sub=levels_text(evidence,used)
                if unclassified:sub=(sub+'\n' if sub else '')+f'Unclassified flow ({money(unclassified)}) not shown'
                left=.3;plotted=True
        elif kind=='gamma_expiry':
            labels=[];values=[];used=[]
            for symbol,row in (evidence.get('gamma') or {}).items():
                for bucket,value in (row.get('buckets') or {}).items():
                    v=number(value.get('net_gex_b') if isinstance(value,dict) else value)
                    if v is not None:
                        labels.append(symbol+'\n'+field_label(bucket));values.append(v)
                        if symbol not in used:used.append(symbol)
            if labels:
                bars=ax.bar(labels,values,color=[GREEN if v>=0 else RED for v in values])
                bar_values(ax,bars,[f'{v:+.2f}' for v in values]);ax.margins(y=.2);ax.axhline(0,color=TEXT,linewidth=.8,alpha=.6)
                ax.set_ylabel('net GEX ($B)')
                legend=[(Patch(fc=c),t) for c,t,ok in ((GREEN,'Positive net gamma',any(v>=0 for v in values)),(RED,'Negative net gamma',any(v<0 for v in values))) if ok]
                neg=sum(v<0 for v in values)
                title=('Dealers are short gamma across every expiry bucket' if neg==len(values) else 'Dealers are long gamma across every expiry bucket' if neg==0
                       else f'Net GEX is mixed: {neg} of {len(values)} expiry buckets are negative')
                sub=levels_text(evidence,used);plotted=True
        elif kind=='sector_credit':
            labels=[];values=[]
            for symbol,row in ((evidence.get('cross_asset') or {}).get('assets') or {}).items():
                p,ref=number(row.get('price')),number(row.get('prev_close'))
                if p and ref:labels.append(symbol);values.append((p/ref-1)*100)
            if labels:
                bars=ax.bar(labels,values,color=[GREEN if v>=0 else RED for v in values])
                bar_values(ax,bars,[f'{v:+.2f}%' for v in values]);ax.margins(y=.2);ax.axhline(0,color=TEXT,linewidth=.8,alpha=.6)
                ax.set_ylabel('Change vs previous close (%)');plotted=True
                hi_i=max(range(len(values)),key=values.__getitem__);lo_i=min(range(len(values)),key=values.__getitem__)
                title=(f'{labels[hi_i]} leads ({values[hi_i]:+.2f}%), {labels[lo_i]} lags ({values[lo_i]:+.2f}%)' if len(values)>1 else f'{labels[0]} is {values[0]:+.2f}% vs previous close')
        elif kind=='market_map':
            profiles=evidence.get('profiles') or {}
            syms=[s for s,r in surfaces.items() if number(r.get('expected_move_low')) and number(r.get('expected_move_high')) and number(r.get('spot'))]
            if syms:
                fig,axs=mk(len(syms));ph=2.5
                seen_legend=set()
                def once(key,label):
                    if key in seen_legend:return None
                    seen_legend.add(key);return label
                # Leron 2026-10-13/14: wall labels (flip/call/put) used to stack on one fixed offset and
                # the put wall reused the EM bar's colour. Labels still fan out one row per level (sorted by
                # x). 2026-10-16 review (#29): SPY (~770) and QQQ (~620) shared one x-axis so each was a
                # tiny cluster; each symbol now has its own panel and x-range, the EM/spot callout is the
                # panel title (it used to float over the dashed lines), and the legend is outside the plot.
                for ax,symbol in zip(axs,syms):
                    row=surfaces[symbol]
                    low,high,spot=number(row.get('expected_move_low')),number(row.get('expected_move_high')),number(row.get('spot'))
                    profile=profiles.get(symbol) or {}
                    val,vah,poc=(number(profile.get(k)) for k in ('val','vah','poc'))
                    gamma=(evidence.get('gamma') or {}).get(symbol) or {}
                    wall_levels=[(label,number(gamma.get(key)),color,key) for key,label,color in [('gamma_flip','flip',AMBER),('call_wall','call wall',RED),('put_wall','put wall',VIOLET)] if number(gamma.get(key)) is not None]
                    xs=[low,high,spot]+[v for v in (val,vah,poc) if v is not None]+[w[1] for w in wall_levels]
                    xlo,xhi=min(xs),max(xs);pad=((xhi-xlo) or 1)*.1;ax.set_xlim(xlo-pad,xhi+pad);ax.set_ylim(-.55,1.5)
                    ax.plot([low,high],[0,0],linewidth=14,alpha=.35,color=CYAN,solid_capstyle='butt',label=once('em','Expected move range'))
                    ax.scatter([spot],[0],color=TEXT,s=90,zorder=5,label=once('spot','Spot (observed)'))
                    if val is not None and vah is not None:ax.plot([val,vah],[-.2,-.2],linewidth=8,color=GREEN,alpha=.5,solid_capstyle='butt',label=once('va','Value area (observed; chop unconfirmed)'))
                    if poc is not None:ax.scatter([poc],[-.2],marker='D',color=GREEN,s=45,zorder=5,label=once('poc','POC (observed)'))
                    for label,level,color,key in wall_levels:
                        ax.plot([level,level],[-.3,.3],color=color,linestyle='--',linewidth=1.5,label=once(key,'Gamma flip' if key=='gamma_flip' else label.title()))
                    wlo,whi=ax.get_xlim()
                    for rank,(label,level,color,key) in enumerate(sorted(wall_levels,key=lambda w:w[1])):
                        frac=(level-wlo)/(whi-wlo);ha,dx=('right',-4) if frac>.8 else ('left',4) if frac<.2 else ('center',0)
                        ax.annotate(f'{label} {level:.2f}',(level,.3),xytext=(dx,6+15*rank),textcoords='offset points',color=color,ha=ha,fontsize=10,fontweight='bold')
                    ax.set_yticks([]);ax.grid(axis='y',visible=False)
                    ax.set_title(f'{symbol}  spot {spot:.2f}  ·  expected move {low:.2f} to {high:.2f}',color=TEXT,fontsize=12,fontweight='bold',loc='left',pad=8)
                    if ax is axs[-1]:ax.set_xlabel('Underlying price ($)')
                title=' and '.join(syms)+' against today\'s expected move';plotted=True;ax=axs[0]
        elif kind=='baseline_comparison':
            current=evidence.get('comparison') or {};previous=evidence.get('prior_comparison') or {}
            eq=[];vx=[]
            for symbol,row in current.items():
                value=number(row.get('price_change_pct'))
                if value is not None:(vx if symbol.upper().lstrip('^').startswith('VIX') else eq).append((symbol,value))
            groups=[g for g in (eq,vx) if g]
            if groups:
                fig,axs=mk(len(groups));ph=2.6 if len(groups)>1 else 3.2
                for ax,g in zip(axs,groups):
                    labels=[s for s,_ in g];positions=list(range(len(labels)))
                    now=ax.bar([p-.18 for p in positions],[v for _,v in g],width=.36,color=CYAN,label='Morning to now')
                    bar_values(ax,now,[f'{v:+.2f}%' for _,v in g])
                    prior_vals=[number((previous.get(s) or {}).get('price_change_pct')) for s in labels]
                    if any(v is not None for v in prior_vals):
                        pr=ax.bar([p+.18 for p in positions],[v if v is not None else float('nan') for v in prior_vals],width=.36,color=GREEN,label='Prior hour to now')
                        bar_values(ax,pr,[f'{v:+.2f}%' if v is not None else '' for v in prior_vals])
                    ax.set_xticks(positions,labels);ax.margins(y=.25);ax.axhline(0,color=TEXT,linewidth=.8,alpha=.6)
                    ax.set_ylabel('Price change (%)' if g is eq else 'VIX change (%)')
                    if len(groups)>1:ax.set_title('Stocks' if g is eq else 'VIX (own scale)',color=TEXT,fontsize=12,fontweight='bold',loc='left',pad=6)
                lead=(eq or vx)[:2]
                title='Since the morning: '+', '.join(f'{s} {v:+.2f}%' for s,v in lead);plotted=True;ax=axs[0]
        elif kind=='paper_equity_drawdown':
            hist=(evidence.get('paper') or {}).get('equity_history') or []
            if hist:
                ax.plot(range(len(hist)),[r['equity'] for r in hist],label='Realized paper P&L',color=GREEN,linewidth=2.5)
                ax.fill_between(range(len(hist)),[r['drawdown'] for r in hist],0,color=RED,alpha=.4,label='Drawdown');ax.set_xlabel('Closed paper trades');ax.set_ylabel('$');plotted=True
                title=f'Paper P&L is ${hist[-1]["equity"]:,.2f} over {len(hist)} closed trades'
        elif kind=='event_risk':
            events=evidence.get('events') or []
            if events:
                labels=[textwrap.shorten(r['name'],width=28,placeholder='…')+'\n'+str(r['datetime'])[:16]+(' • estimated' if not r.get('verified') else ' • verified') for r in events[:10]]
                ax.barh(labels,[3 if r.get('impact')=='HIGH' else 2 for r in events[:10]],color=AMBER);ax.invert_yaxis()
                ax.tick_params(axis='y',labelsize=10);ax.set_xlabel('Scheduled impact class (not a probability)');left=.4;plotted=True
                title=f'{len(events[:10])} scheduled events ahead, {sum(r.get("impact")=="HIGH" for r in events[:10])} high impact'
        elif kind=='volume_profile':
            profs=[(s,r) for s,r in (evidence.get('profiles') or {}).items() if r.get('bins')]
            if profs:
                fig,axs=mk(len(profs));ph=2.6;most=0
                for ax,(symbol,row) in zip(axs,profs):
                    bins=row['bins']
                    ax.plot([r['price'] for r in bins],[r['volume'] for r in bins],color=SYM_COLOR.get(symbol,CYAN),linewidth=2)
                    ax.yaxis.set_major_formatter(FuncFormatter(lambda v,_:compact(v)));ax.set_ylabel('Shares');ax.set_xlabel('Traded price ($)')
                    ax.text(.01,.93,symbol,transform=ax.transAxes,color=TEXT,fontsize=12,fontweight='bold',va='top')
                    lv=level_list(evidence,symbol)
                    if lv:most=max(most,draw_levels(ax,lv))
                extra=most;title='Where '+' and '.join(s for s,_ in profs)+' volume traded';plotted=True;ax=axs[0]
        if not plotted:
            ax.text(.5,.5,'No verified observations for this panel\nSee Data Integrity for source status',transform=ax.transAxes,ha='center',va='center',color=TEXT,fontsize=14)
            title=kind.replace('_',' ').title();sub='';legend=[];extra=0.0
        group='surface' if kind in ('market_map','surface','smile_term','term_structure','baseline_comparison') else 'gamma' if kind=='gamma_expiry' else 'profiles' if kind=='volume_profile' else 'flow' if kind=='flow' else None
        clocks=[stamp(s,r) for s,r in (evidence.get(group) or {}).items()] if group else [stamp(s,r) for s,r in (evidence.get('cross_asset',{}).get('assets') or {}).items()][:3] if kind=='sector_credit' else []
        footer=' · '.join(clocks[:2]) if clocks else 'Source times and coverage are in the report. Event times are estimates where marked; paper results are simulations.'
        finish(fig,axs,title,sub,legend,footer,ph=ph,extra=extra,left=left)
        out=io.BytesIO();fig.savefig(out,format='png',facecolor=BG);return out.getvalue(),plotted
