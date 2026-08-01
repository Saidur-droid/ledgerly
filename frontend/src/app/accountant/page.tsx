"use client";
import {useEffect,useState} from "react";
import Link from "next/link";
import {ArrowLeft,Building2,CheckCircle2,Clock3,FileWarning,RefreshCw} from "lucide-react";
import {createAccountantWorkspace,getAccountantDashboard,hasSession,type AccountantDashboard} from "@/lib/api";

const cards=[
  ["complete","Complete",CheckCircle2],
  ["missing_data","Missing data",FileWarning],
  ["reconciliation_pending","Reconciliation pending",RefreshCw],
  ["report_due","Report due",Clock3],
] as const;

export default function AccountantPage(){
 const [data,setData]=useState<AccountantDashboard|null>(null),[error,setError]=useState(""),[busy,setBusy]=useState(false);
 async function load(){try{setData(await getAccountantDashboard());setError("")}catch(e){setError(e instanceof Error?e.message:"Unable to load accountant workspace.")}}
 useEffect(()=>{if(!hasSession()){location.href="/login";return}void Promise.resolve().then(load)},[]);
 async function addClient(){const name=prompt("Client workspace name");if(!name)return;setBusy(true);try{await createAccountantWorkspace(name,"USD");await load()}catch(e){setError(e instanceof Error?e.message:"Unable to add client.")}finally{setBusy(false)}}
 return <main className="accountant-shell"><header className="accountant-header"><Link href="/" aria-label="Back to dashboard"><ArrowLeft size={18}/></Link><div><span>ACCOUNTANT WORKSPACE</span><h1>Client closing desk</h1><p>Review every client, period, approval, and report from one controlled workspace.</p></div><button onClick={addClient} disabled={busy}><Building2 size={16}/>Add client</button></header>
 {error&&<div className="studio-error" role="alert">{error}<button onClick={load}>Retry</button></div>}
 <section className="accountant-summary" aria-label="Closing status summary">{cards.map(([key,label,Icon])=><article key={key} data-status={key}><Icon size={18}/><div><strong>{data?.summary[key]??0}</strong><span>{label}</span></div></article>)}</section>
 <section className="accountant-table" aria-label="Client workspace periods"><div className="accountant-table-head"><span>Client</span><span>Period</span><span>Files</span><span>Checklist</span><span>Status</span></div>{data?.periods.length?data.periods.map(period=>{const client=data.clients.find(item=>item.id===period.workspace_id);const done=period.checklist.filter(item=>item.status==="approved").length;return <article key={period.id}><span><Building2 size={15}/><b>{client?.name??"Client"}</b><small>{client?.role}</small></span><span>{period.period}</span><span>{period.file_ids.length}</span><span>{done}/{period.checklist.length}</span><span className={`workspace-state ${period.status}`}>{period.status.replaceAll("_"," ")}</span></article>}):<div className="accountant-empty"><Building2 size={24}/><h2>No client periods yet</h2><p>Add a client workspace, then start its monthly closing workflow.</p></div>}</section>
 </main>
}
