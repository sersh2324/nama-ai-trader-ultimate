"""Visual treatment shared by the NAMA stock workspace."""

WORKSPACE_STYLE = """
<style>
.block-container { max-width: 1220px; padding-top: 3.2rem; }
.nama-brand {
    display: flex; justify-content: space-between; align-items: center;
    min-height: 3.5rem; margin-bottom: .45rem; padding: .5rem 0;
    border-bottom: 1px solid #324A52;
}
.nama-brand h1 { color: #64E4B5; font-size: 1.55rem; letter-spacing: .1em; margin: 0; padding: 0; }
.nama-brand span { color: #B7CDD1; font-size: .87rem; }
[data-testid="stMainBlockContainer"] [data-testid="stMarkdownContainer"],
[data-testid="stMainBlockContainer"] [data-testid="stWidgetLabel"],
[data-testid="stMainBlockContainer"] [data-testid="stCaptionContainer"] {
    text-align: right; direction: rtl;
}
[data-testid="stMetric"] { padding: .6rem .9rem; min-width: 0; }
[data-testid="stMetricValue"] { font-size: clamp(1.15rem,4vw,1.85rem); }
[data-testid="stMetricValue"] > div { overflow: visible; }
[data-testid="stTabs"] [role="tablist"] { gap: .65rem; }
[data-testid="stTabs"] [role="tab"] { min-height: 2.65rem; white-space: nowrap; }
.st-key-chart_quick_interval [role="radiogroup"],
.st-key-market [role="radiogroup"] { gap: .35rem; flex-wrap: wrap; }
.st-key-chart_quick_interval [role="radiogroup"] label,
.st-key-market [role="radiogroup"] label {
    padding: .4rem .58rem; background: #152A34; border: 1px solid #324A52;
    border-radius: .65rem; margin: 0; min-height: 2.55rem;
}
.st-key-chart_quick_interval [role="radiogroup"] label:has(input:checked),
.st-key-market [role="radiogroup"] label:has(input:checked) {
    background: #234739; border-color: #64E4B5;
}
.st-key-scenario_card {
    background: #122730; border-radius: .9rem; border-color: #35545A;
}
@media (max-width: 640px) {
    .block-container { padding: 2.8rem .8rem 1rem; }
    [data-testid="stTabs"] [role="tablist"] { gap: .45rem; }
    [data-testid="stTabs"] [role="tab"] { font-size: .84rem; }
    [data-testid="stMetric"] { padding: .2rem .35rem; }
    .st-key-chart_quick_interval [role="radiogroup"] { gap: .24rem; }
    .st-key-chart_quick_interval [role="radiogroup"] label { padding: .3rem .39rem; }
    [data-testid="stMainBlockContainer"] > [data-testid="stVerticalBlock"] { gap: .75rem; }
}
</style>
<div class="nama-brand"><h1>NAMA</h1><span lang="ar" dir="rtl">نماء للأسهم</span></div>
"""
