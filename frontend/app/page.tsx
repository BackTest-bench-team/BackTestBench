"use client";

import { useEffect, useState } from "react";

type Metrics = {
  strategy_id: string;
  instrument: string;
  total_pnl: number;
  sharpe_ratio: number;
  max_drawdown: number;
  win_rate: number;
  deposit_baseline_pnl: number;
};


type EquityPoint = {
  date: string;
  value: number;
};


export default function Home() {

  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [equity, setEquity] = useState<EquityPoint[]>([]);

  const [status, setStatus] = useState(
    "Waiting for pipeline"
  );


  async function loadData() {

    try {

      setStatus("Loading metrics...");


      const metricsResponse =
        await fetch("/api/metrics");


      const metricsData =
        await metricsResponse.json();


      setMetrics(metricsData.metrics);


      setEquity(metricsData.equity);


      setStatus(
        "Analytics loaded"
      );


    } catch(error) {

      console.error(error);

      setStatus(
        "Pipeline error"
      );
    }

  }



  useEffect(() => {

    loadData();

    // обновление каждые 5 секунд
    const timer =
      setInterval(loadData,5000);


    return () =>
      clearInterval(timer);


  },[]);



  return (

    <main
      style={{
        padding:"40px",
        fontFamily:"Arial"
      }}
    >

      <h1>
        BackTest Bench MVP
      </h1>


      <button
        onClick={loadData}
        style={{
          padding:"10px 20px",
          marginBottom:"20px"
        }}
      >

        Run backtest

      </button>



      <h3>
        Pipeline status:
      </h3>


      <p>
        {status}
      </p>




      <h2>
        Metrics
      </h2>


      {
        metrics && (

          <div
            style={{
              display:"grid",
              gridTemplateColumns:
              "repeat(3,200px)",
              gap:"20px"
            }}
          >


            <Card
              title="P&L"
              value={
                metrics.total_pnl
              }
            />


            <Card
              title="Sharpe"
              value={
                metrics.sharpe_ratio
              }
            />


            <Card
              title="Max drawdown"
              value={
                metrics.max_drawdown * 100 + "%"
              }
            />


            <Card
              title="Win rate"
              value={
                metrics.win_rate * 100 + "%"
              }
            />


            <Card
              title="Deposit"
              value={
                metrics.deposit_baseline_pnl
              }
            />


          </div>

        )

      }



      <h2>
        Portfolio equity
      </h2>



      <div
        style={{
          border:"1px solid gray",
          padding:"20px",
          width:"600px"
        }}
      >


        {
          equity.map(
            (p,index)=>(

              <div key={index}>

                {p.date}
                :
                {" "}
                {p.value}

              </div>

            )
          )

        }


      </div>


    </main>

  );


}



function Card(
{
 title,
 value
}:{
 title:string,
 value:number|string
}

){


return (

<div

style={{

border:"1px solid #ccc",

padding:"20px",

borderRadius:"8px"

}}

>

<h3>
{title}
</h3>


<h2>
{value}
</h2>


</div>

)


}