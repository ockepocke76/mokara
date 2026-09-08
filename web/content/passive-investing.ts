export const PASSIVE_INVESTING_MD = `### The Research Is Clear: Passive Beats Active

This simulator uses **market index returns** (via historical bootstrap or parametric models) 
rather than individual stock-picking. Why? Decades of academic research shows that for retail 
investors, passive index investing consistently outperforms active stock selection.

---

### Key Findings from Research

#### 📊 Performance Gap

- **90% of active fund managers underperform** their benchmark index over 15-year periods 
  ([SPIVA U.S. Scorecard](https://www.spglobal.com/spdji/en/research-insights/spiva/))

- **Only 3% of actively managed funds** demonstrate genuine skill (not luck) after costs 
  ([Fama & French, 2010, Journal of Finance](https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1540-6261.2010.01598.x))

- Active funds that DO beat the index have **less than 25% probability** of repeating 
  that success over subsequent periods 
  ([Morningstar Persistence Study](https://www.morningstar.com/lp/active-passive-barometer))

#### 💰 Cost Impact

- Average expense ratios compound to destroy **30-50% of returns** over a 30-year retirement 
  ([Bogle, 2014](https://johncbogle.com/wordpress/wp-content/uploads/2010/04/FAJ-All-In-Investment-Expenses-Jan-Feb-2014.pdf))

- **Comparison:**
  - Active mutual funds: 0.50-1.00% annual fees
  - Index funds: 0.03-0.10% annual fees
  - **Over 30 years**: A 1% fee difference reduces final wealth by ~25%

#### 🏛️ Tax Efficiency

- Active management creates **1-2% annual tax drag** from frequent trading 
  ([Dickson, Shoven, & Sialm, 2000](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=228143))

- Index funds/ETFs have **~1% lower annual tax burden** due to minimal turnover 
  ([Moussawi, Shen & Velthuis, 2025, Review of Financial Studies](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3744519))

---

### What This Means for Investors

**The math is brutal for active investors:**

Starting with $1,000,000 over 30 years at 8% gross returns:

| Strategy | Annual Costs | Net Return | Final Value | Cost of Active |
|----------|--------------|------------|-------------|----------------|
| **Index Fund** (0.05% fee + 0.02% tax) | **0.07%** | 7.93% | **$9.9M** | — |
| **Active Fund** (1.0% fee + 0.5% tax) | **1.5%** | 6.5% | **$6.6M** | **-$3.3M** |

> **$1M × (1.0793)³⁰ = $9.9M** vs **$1M × (1.065)³⁰ = $6.6M**  
> The 1.43% annual cost difference compounds to a **$3.3M loss** (33% of your potential wealth)

---

### What This Simulator Does Instead

Rather than trying to predict which stocks will outperform (where 90% fail), we use **broad market 
index returns** (via bootstrap resampling of historical data OR parametric models) and focus on:

✅ **Withdrawal Strategy**: How much to withdraw and when (Trinity, Buy-Borrow-Die, etc.)  
✅ **Custom Strategy Design**: Build your own strategies with AI assistance  
✅ **Tax Optimization**: ISK vs Capital Gains, timing of realizations  
✅ **Risk Management**: Portfolio survival probability, tail risk analysis  
✅ **Asset Allocation**: Systematic rebalancing, not market timing  

🛠️ **Design Your Own Strategy**: Don't like the built-in strategies? Use our **AI-powered Strategy Designer** 
to create custom withdrawal strategies in plain English. Describe what you want, and the AI generates 
executable code that runs in your simulations.

**Why?** Because research shows these factors are:
- **Controllable** (unlike market returns)
- **Persistent** (work across market conditions)
- **High-impact** (can improve outcomes by 1-3% annually)

---

### 🏆 Collective Intelligence: Wisdom of the Crowd

While picking individual stocks is a losing game, **designing better withdrawal strategies** is a 
solvable problem—and one where community collaboration can outperform professional managers.

**How it works:**
- Users create custom strategies using the AI-powered designer
- All strategies are stress-tested across 8 standardized market scenarios
- Results are ranked on a **public leaderboard** by risk-adjusted "Excellence Score"
- Top strategies can be studied, adapted, and improved by others

**Why this matters:**

Research on prediction markets ([Surowiecki, 2004](https://en.wikipedia.org/wiki/The_Wisdom_of_Crowds)) 
shows that diverse groups often outperform experts when:
- There's a **clear scoring mechanism** (our Excellence Score)
- Contributors are **diverse and independent** (users from different backgrounds)
- Contributions are **aggregated effectively** (leaderboard ranking)

🚀 **The Vision**: As thousands of users compete to create optimal strategies, 
we harness collective intelligence to discover withdrawal approaches that may 
outperform what any single financial advisor could design.

---

### Exceptions & Nuances

⚠️ **The research doesn't say skill is impossible**, just extremely rare:

- Warren Buffett proved it's POSSIBLE (but his advice? ["Put 90% in index funds"](https://www.investopedia.com/articles/personal-finance/121815/buffetts-bet-hedge-funds-year-eight-brka-brkb.asp))
- High "active share" managers CAN outperform ([Cremers & Petajisto, 2009](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=891719))
- **BUT**: Identifying them *ex-ante* (before they outperform) is nearly impossible

**For 99% of investors:** Passive indexing + smart withdrawal strategy beats stock-picking.

---

<details>
<summary><strong>Comprehensive Research References</strong></summary>


#### Industry Reports (Updated Annually)

1. **SPIVA U.S. Scorecard** (S&P Dow Jones Indices)  
   [https://www.spglobal.com/spdji/en/research-insights/spiva/](https://www.spglobal.com/spdji/en/research-insights/spiva/)  
   *Tracks % of active funds that underperform benchmarks*

3. **Morningstar Active/Passive Barometer**  
   [https://www.morningstar.com/lp/active-passive-barometer](https://www.morningstar.com/lp/active-passive-barometer)  
   *Measures active fund success rates and persistence*

#### Academic Research

4. **Fama, E. F., & French, K. R. (2010)**  
   "Luck versus Skill in the Cross-Section of Mutual Fund Returns"  
   *Journal of Finance*, 65(5), 1915-1947.  
   [https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1540-6261.2010.01598.x](https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1540-6261.2010.01598.x)  
   *Proves most outperformance is luck, not skill*

5. **Sharpe, W. F. (1991)**  
   "The Arithmetic of Active Management"  
   *Financial Analysts Journal*, 47(1), 7-9.  
   [https://www.tandfonline.com/doi/abs/10.2469/faj.v47.n1.7](https://www.tandfonline.com/doi/abs/10.2469/faj.v47.n1.7)  
   *Mathematical proof: Active investors must underperform on average*

6. **Malkiel, B. G. (2003)**  
   "Passive Investment Strategies and Efficient Markets"  
   *European Financial Management*, 9(1), 1-10.  
   [https://onlinelibrary.wiley.com/doi/abs/10.1111/1468-036X.00205](https://onlinelibrary.wiley.com/doi/abs/10.1111/1468-036X.00205)  
   *Comprehensive evidence for market efficiency*

7. **Cremers, M., & Petajisto, A. (2009)**  
   "How Active Is Your Fund Manager? A New Measure That Predicts Performance"  
   *Review of Financial Studies*, 22(9), 3329-3365.  
   [https://papers.ssrn.com/sol3/papers.cfm?abstract_id=891719](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=891719)  
   *High active share CAN work, but hard to identify ex-ante*

#### Tax & Cost Analysis

8. **Dickson, J. M., Shoven, J. B., & Sialm, C. (2000)**  
   "Tax Externalities of Equity Mutual Funds"  
   *National Bureau of Economic Research Working Paper*, No. 7669.  
   [https://www.nber.org/papers/w7669](https://www.nber.org/papers/w7669)  
   *Quantifies 1-2% annual tax drag from active trading*

9. **Moussawi, R., Shen, K., & Velthuis, R. (2025)**  
   "The Role of Taxes in the Rise of ETFs"  
   *Review of Financial Studies*, 38(10), 3094-3129.  
   [https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3744519](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3744519)  
   *ETFs have ~1% lower annual tax burden than mutual funds*

11. **Ellis, C. D. (2013)**  
    *Winning the Loser's Game* (6th Edition)  
    McGraw-Hill. ISBN: 978-0071798143  
    *Why trying to beat the market is a losing strategy*

12. **Swedroe, L. E., & Grogan, K. (2014)**  
    *Reducing the Risk of Black Swans*  
    BAM Alliance Press. ISBN: 978-0692281659  
    *Evidence-based approach to portfolio design*

</details>


---

### The Bottom Line

This simulator is built on the principle that **your withdrawal strategy matters more than 
your stock picks.** The research overwhelmingly supports this approach.

Focus on what you can control:
- How much to withdraw
- When to realize gains (tax timing)
- How to fund consumption (sell vs borrow)
- How to manage risk (success probability)

Let the market deliver returns. You focus on not running out of money.`;
