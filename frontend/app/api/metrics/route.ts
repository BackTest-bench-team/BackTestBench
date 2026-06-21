import { NextResponse } from "next/server";


export async function GET(){


const metrics = {

strategy_id:"rsi_strategy",

instrument:"SBER",

total_pnl:125000,

sharpe_ratio:1.42,

max_drawdown:0.12,

win_rate:0.63,

deposit_baseline_pnl:80000

};



const equity = [

{
date:"2026-01-01",
value:100000
},

{
date:"2026-02-01",
value:108000
},

{
date:"2026-03-01",
value:125000
},

{
date:"2026-04-01",
value:119000
},

{
date:"2026-05-01",
value:145000
}

];



return NextResponse.json({

metrics,

equity

});


}