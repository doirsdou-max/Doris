"""卡型分析：两年季度订单明细 → 分年级客单价/扩科率/卡型结构拆解 + 结构图。

用法：
  python3 kaxing.py --last 去年.xlsx --this 今年.xlsx \
      --min-cid-last 255400 --min-cid-this 287200 \
      --label-last 25年Q3 --label-this 26年Q3 --gift-addback 2025H2 --out ./out
"""
import argparse
import os

import pandas as pd

HS = ['高一', '高二', '高三']
COLS = ['cid', 'oid', 'subj', 'grade', 'base', 'uid', 'ograde', 'card', 'pkg', 'rev', 'refund', 'flag']

CARD_MAP = {'H1加油包-H2半年卡': '含加油包全体系直通卡', 'H1加油包-一轮卡': '含加油包全体系直通卡',
            'H1半年卡-秋实卡': '全体系直通卡(秋实+H1)', '直通卡': '名校直通卡',
            '冬习卡-秋实卡': '秋冬衔接卡', 'H2半年卡': 'H2半年卡', '一轮卡': '一轮卡',
            '秋实卡': '秋实卡', '夏研卡': '夏研卡'}
CARD_GROUP = {'含加油包全体系直通卡': '高价直通卡', '全体系直通卡(秋实+H1)': '高价直通卡', '名校直通卡': '高价直通卡',
              '秋冬衔接卡': '秋冬衔接卡', 'H2半年卡': '单学期主卡', '一轮卡': '单学期主卡',
              '秋实卡': '秋实卡', '夏研卡': '夏研卡', '其他': '其他'}

# 决胜卡赠科分摊：明细中付费科目营收被拆出一部分给赠科（赠科行不在表里），按价格表加回
GIFT_ADDBACK = {
    '2025H2': {3030: 750, 2480: 1000, 2355: 1125, 2580: 900, 2730: 750,
               2930: 750, 2380: 1000, 2255: 1125, 2630: 750},
}


def load(path, min_cid, addback):
    d = pd.read_excel(path)
    d.columns = COLS[:len(d.columns)]
    if min_cid:
        d = d[d.cid >= min_cid]
    # 转化课实际年级 = 该课程学员所购正价课的多数年级
    x = d[d.grade.isin(HS)]
    cg = (x.groupby(['cid', 'grade']).uid.nunique().reset_index()
          .sort_values('uid', ascending=False).drop_duplicates('cid').set_index('cid').grade)
    d['cg'] = d.cid.map(cg)
    hs = d[d.ograde.isin(HS)]
    print(f'  {os.path.basename(path)}: 行{len(d)} 订单号{d.oid.min()}~{d.oid.max()} '
          f'原始年级与推断年级一致率{(hs.ograde == hs.cg).mean():.1%}')
    d = d[d.cg.isin(HS)].copy()
    d['net'] = d.rev - d.refund
    if addback:
        m = (d.cg == '高一') & (d.card == 'H2半年卡') & (d.pkg == '全体系决胜卡') & d.rev.isin(addback)
        d.loc[m, 'net'] += d.loc[m, 'rev'].map(addback) * (1 - d.loc[m, 'refund'] / d.loc[m, 'rev'])
        print(f'  赠科营收加回：{int(m.sum())}行')
    paid = d[d.rev > 0].groupby(['cg', 'uid', 'subj']).size().index
    d = d[d.set_index(['cg', 'uid', 'subj']).index.isin(paid)]
    d['g'] = d.card.map(CARD_MAP).fillna('其他')
    k = d.groupby(['cg', 'uid', 'subj', 'g']).net.sum().reset_index().sort_values('net', ascending=False)
    lab = k.drop_duplicates(['cg', 'uid', 'subj']).set_index(['cg', 'uid', 'subj']).g
    s = d.groupby(['cg', 'uid', 'subj']).net.sum().to_frame()
    s['g'] = lab
    return s.reset_index()


def kpi(x):
    h = x.uid.nunique()
    n = len(x.drop_duplicates(['uid', 'subj']))
    return h, x.net.sum() / h, n / h, x.net.sum() / len(x)


def report(A, B, la, lb):
    rows = []
    for G in HS + ['合计']:
        a = A if G == '合计' else A[A.cg == G]
        b = B if G == '合计' else B[B.cg == G]
        (h0, c0, k0, p0), (h1, c1, k1, p1) = kpi(a), kpi(b)
        rows.append([G, h0, h1, round(c0), round(c1), f'{c1/c0-1:+.1%}', round(k0, 3), round(k1, 3), round(p0), round(p1)])
    print(pd.DataFrame(rows, columns=['年级', f'人头{la}', f'人头{lb}', f'客单{la}', f'客单{lb}', '同比',
                                      f'扩科{la}', f'扩科{lb}', f'每科{la}', f'每科{lb}']).to_string(index=False))
    for G in HS:
        a, b = A[A.cg == G], B[B.cg == G]
        t = pd.concat([x.groupby('g').net.agg(['size', 'mean']).assign(share=lambda z: z['size'] / z['size'].sum())[['share', 'mean']]
                       .add_prefix(p) for p, x in [(la + '_', a), (lb + '_', b)]], axis=1).fillna(0)
        p0, p1 = a.net.mean(), b.net.mean()
        mix = (t[lb + '_share'] * t[la + '_mean']).sum() - p0
        t['结构贡献'] = (t[lb + '_share'] - t[la + '_share']) * (t[la + '_mean'] - p0)
        print(f'\n== {G} 每科 {p0:.0f}→{p1:.0f}：卡型结构 {mix:+.0f}，同卡价格 {p1-p0-mix:+.0f}')
        for lab, x in [(la, a), (lb, b)]:
            dist = x.groupby('uid').size().clip(upper=4).value_counts(normalize=True).sort_index()
            print(f'   {lab} 报科数(1/2/3/4+)：' + ' / '.join(f'{v:.1%}' for v in dist))
        print(t.sort_values(la + '_share', ascending=False).round(3).to_string())


def chart(A, B, la, lb, out):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib import font_manager as fm
    for f in ['/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc', '/System/Library/Fonts/PingFang.ttc']:
        if os.path.exists(f):
            fm.fontManager.addfont(f)
            plt.rcParams['font.family'] = fm.FontProperties(fname=f).get_name()
            break
    order = ['高价直通卡', '秋冬衔接卡', '单学期主卡', '秋实卡', '夏研卡', '其他']
    names = ['高价直通卡', '秋冬衔接卡', 'H2半年卡 / 一轮卡', '秋实卡', '夏研卡', '其他']
    col = ['#eb6834', '#b9b2e3', '#2a78d6', '#a9c6ea', '#1baf7a', '#e4e2dc']
    ink, ink2, bg = '#1f1f1d', '#6b6a65', '#ffffff'
    fig, ax = plt.subplots(figsize=(12, 7.2))
    fig.patch.set_facecolor(bg)
    y, yt, yl = 0, [], []
    for G in HS:
        top = y
        cs = []
        for lab, D in [(la, A), (lb, B)]:
            x = D[D.cg == G]
            cs.append(kpi(x)[1])
            sh = x.g.map(CARD_GROUP).value_counts(normalize=True).reindex(order).fillna(0) * 100
            left = 0
            for c, cl in zip(order, col):
                v = sh[c]
                if v > 0:
                    ax.barh(y, v, left=left, height=0.62, color=cl, edgecolor=bg, linewidth=2)
                    if v >= 2.5:
                        tc = '#ffffff' if cl in ('#eb6834', '#2a78d6', '#1baf7a') else ink
                        ax.text(left + v / 2, y, f'{v:.0f}%', ha='center', va='center', fontsize=12 if v >= 6 else 10, color=tc)
                left += v
            yt.append(y); yl.append(lab)
            y += 0.8
        ax.text(-11, top + 0.4, G, ha='right', va='center', fontsize=17, color=ink, fontweight='bold')
        ax.text(101.5, top + 0.4, f'客单价\n{cs[0]:.0f} → {cs[1]:.0f}  {cs[1]/cs[0]-1:+.1%}', ha='left', va='center',
                fontsize=12, color=ink2, linespacing=1.5)
        y += 0.7
    ax.set_yticks(yt); ax.set_yticklabels(yl, fontsize=12, color=ink2)
    ax.invert_yaxis(); ax.set_xlim(0, 100); ax.set_xticks([])
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(left=False)
    fig.legend([plt.Rectangle((0, 0), 1, 1, color=c) for c in col], names, loc='lower center', ncol=6,
               frameon=False, fontsize=12, handlelength=1.2, columnspacing=1.6, bbox_to_anchor=(0.47, 0.03))
    fig.text(0.04, 0.94, '【标题写结论，按实际结果修改】', fontsize=20, color=ink, fontweight='bold')
    fig.text(0.04, 0.895, f'{lb} vs {la} · 各卡型占学科人次比例 · 高价直通卡＝含加油包全体系直通卡、全体系直通卡（秋实+H1）、名校直通卡',
             fontsize=11, color=ink2)
    plt.subplots_adjust(left=0.15, right=0.82, top=0.85, bottom=0.12)
    p = os.path.join(out, '卡型结构同比.png')
    plt.savefig(p, dpi=200, facecolor=bg)
    print('\n图：', p)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--last', required=True)
    ap.add_argument('--this', dest='this', required=True)
    ap.add_argument('--min-cid-last', type=int, default=0)
    ap.add_argument('--min-cid-this', type=int, default=0)
    ap.add_argument('--label-last', default='去年')
    ap.add_argument('--label-this', default='今年')
    ap.add_argument('--gift-addback', default='', help='去年数据的赠科加回规则，如 2025H2；无则留空')
    ap.add_argument('--out', default='.')
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    print('读取与核对：')
    A = load(a.last, a.min_cid_last, GIFT_ADDBACK.get(a.gift_addback))
    B = load(a.this, a.min_cid_this, None)
    report(A, B, a.label_last, a.label_this)
    chart(A, B, a.label_last, a.label_this, a.out)
