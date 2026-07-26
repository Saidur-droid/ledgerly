"use client";

import { useState } from "react";
import { ArrowRight, Check, Eye, EyeOff, Sparkles, TrendingUp } from "lucide-react";
import Link from "next/link";

export default function LoginPage() {
  const [showPassword, setShowPassword] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    window.location.href = "/";
  }

  return (
    <main className="login-shell">
      <section className="login-story">
        <Link className="login-brand" href="/"><span><TrendingUp size={18} /></span>Ledgerly</Link>
        <div className="story-copy">
          <span className="story-kicker"><Sparkles size={14} />BUSINESS INTELLIGENCE, MADE HUMAN</span>
          <h1>Your business has a story.<br /><em>Now it can tell you.</em></h1>
          <p>Turn scattered spreadsheets and statements into a clear, living view of how your business is doing.</p>
          <div className="story-points">
            <span><Check size={14} />Understand performance in plain language</span>
            <span><Check size={14} />Remember every upload and every change</span>
            <span><Check size={14} />Ask questions grounded only in your data</span>
          </div>
        </div>
        <p className="story-quote">“Clarity is the beginning of every better business decision.”</p>
      </section>
      <section className="login-form-side">
        <form className="login-card" onSubmit={handleSubmit}>
          <div className="mobile-login-brand"><TrendingUp size={17} />Ledgerly</div>
          <span className="welcome-pill">WELCOME BACK</span>
          <h2>Sign in to Ledgerly</h2>
          <p>Continue the conversation with your business.</p>
          <label>Email address<input type="email" required value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@company.com" /></label>
          <label>Password<div className="password-input"><input type={showPassword ? "text" : "password"} required minLength={8} value={password} onChange={(event) => setPassword(event.target.value)} placeholder="Enter your password" /><button type="button" aria-label="Show password" onClick={() => setShowPassword((value) => !value)}>{showPassword ? <EyeOff size={16} /> : <Eye size={16} />}</button></div></label>
          <div className="login-options"><label><input type="checkbox" />Remember me</label><a href="#">Forgot password?</a></div>
          <button className="sign-in-button">Sign in <ArrowRight size={16} /></button>
          <div className="login-divider"><span>or</span></div>
          <button type="button" className="demo-button" onClick={() => { window.location.href = "/"; }}>Explore the live demo</button>
          <p className="signup-copy">New to Ledgerly? <a href="#">Create your account</a></p>
          <small className="security-copy">Your business data is encrypted in transit and at rest.</small>
        </form>
      </section>
    </main>
  );
}
