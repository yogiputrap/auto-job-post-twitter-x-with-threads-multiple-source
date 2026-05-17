"""Monitoring dashboard for the Job Vacancy Twitter Bot.

Clean UI with sidebar navigation, stat cards, and job listing table.
Run with: python dashboard.py (default port 5000)
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import traceback
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, jsonify, render_template_string, request
import httpx

app = Flask(__name__)

DB_PATH = os.environ.get("DB_PATH", "posted_jobs.sqlite")
LOG_PATH = os.environ.get("LOG_PATH", "bot.log")

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Job Bot Dashboard</title>
    <link href="https://fonts.googleapis.com/icon?family=Material+Icons+Outlined" rel="stylesheet">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif; background: #f8fafc; color: #1e293b; display: flex; min-height: 100vh; }

        /* Sidebar */
        .sidebar { width: 240px; background: #fff; border-right: 1px solid #e2e8f0; padding: 1.5rem 0; display: flex; flex-direction: column; position: fixed; height: 100vh; z-index: 100; transition: transform 0.3s; }
        .sidebar-brand { padding: 0 1.5rem; margin-bottom: 2rem; display: flex; align-items: center; gap: 0.75rem; }
        .sidebar-brand .icon { width: 36px; height: 36px; background: #10b981; border-radius: 10px; display: flex; align-items: center; justify-content: center; color: white; font-size: 1.2rem; }
        .sidebar-brand h2 { font-size: 1.1rem; font-weight: 700; color: #1e293b; }
        .sidebar-section { font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.08em; color: #94a3b8; padding: 0 1.5rem; margin: 1.5rem 0 0.5rem; }
        .sidebar-nav { list-style: none; }
        .sidebar-nav li a { display: flex; align-items: center; gap: 0.75rem; padding: 0.65rem 1.5rem; color: #64748b; text-decoration: none; font-size: 0.9rem; font-weight: 500; transition: all 0.15s; border-left: 3px solid transparent; }
        .sidebar-nav li a:hover { background: #f1f5f9; color: #1e293b; }
        .sidebar-nav li a.active { background: #ecfdf5; color: #10b981; border-left-color: #10b981; font-weight: 600; }
        .sidebar-nav li a .nav-icon { font-size: 1.1rem; width: 20px; text-align: center; }

        /* Main */
        .main { margin-left: 240px; flex: 1; padding: 2rem 2.5rem; }
        .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 2rem; }
        .header h1 { font-size: 1.5rem; font-weight: 700; color: #1e293b; }
        .header p { color: #64748b; font-size: 0.9rem; margin-top: 0.25rem; }
        .header-actions { display: flex; gap: 0.75rem; }
        .btn { border: none; padding: 0.6rem 1.2rem; border-radius: 8px; cursor: pointer; font-size: 0.85rem; font-weight: 600; transition: all 0.15s; display: inline-flex; align-items: center; gap: 0.4rem; }
        .btn-primary { background: #10b981; color: white; }
        .btn-primary:hover { background: #059669; }
        .btn-outline { background: white; color: #64748b; border: 1px solid #e2e8f0; }
        .btn-outline:hover { background: #f8fafc; border-color: #cbd5e1; }
        .btn:disabled { opacity: 0.5; cursor: not-allowed; }

        /* Stat Cards */
        .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 1.25rem; margin-bottom: 2rem; }
        .stat-card { background: white; border-radius: 14px; padding: 1.25rem 1.5rem; border: 1px solid #e2e8f0; display: flex; align-items: center; gap: 1rem; }
        .stat-card .stat-icon { width: 44px; height: 44px; border-radius: 12px; display: flex; align-items: center; justify-content: center; font-size: 1.3rem; }
        .stat-card .stat-icon span { font-size: 22px; }
        .stat-card .stat-icon.green { background: #d1fae5; color: #059669; }
        .stat-card .stat-icon.blue { background: #dbeafe; color: #2563eb; }
        .stat-card .stat-icon.orange { background: #ffedd5; color: #ea580c; }
        .stat-card .stat-icon.purple { background: #ede9fe; color: #7c3aed; }
        .stat-card .stat-info { flex: 1; }
        .stat-card .stat-label { font-size: 0.8rem; color: #64748b; margin-bottom: 0.2rem; }
        .stat-card .stat-value { font-size: 1.5rem; font-weight: 700; color: #1e293b; }
        .stat-card .stat-change { font-size: 0.75rem; color: #10b981; margin-top: 0.2rem; }
        .stat-card .stat-change.negative { color: #ef4444; }

        /* Content Grid */
        .content-grid { display: grid; grid-template-columns: 2fr 1fr; gap: 1.5rem; margin-bottom: 2rem; }
        @media (max-width: 1024px) { .content-grid { grid-template-columns: 1fr; } }

        /* Mobile hamburger */
        .mobile-header { display: none; position: fixed; top: 0; left: 0; right: 0; height: 56px; background: #fff; border-bottom: 1px solid #e2e8f0; z-index: 99; padding: 0 1rem; align-items: center; gap: 0.75rem; }
        .hamburger { background: none; border: none; cursor: pointer; padding: 0.5rem; display: flex; align-items: center; }
        .hamburger span { font-size: 24px; color: #475569; }
        .overlay { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.3); z-index: 99; }

        /* Responsive */
        @media (max-width: 768px) {
            .sidebar { transform: translateX(-100%); }
            .sidebar.open { transform: translateX(0); box-shadow: 4px 0 24px rgba(0,0,0,0.1); }
            .overlay.open { display: block; }
            .mobile-header { display: flex; }
            .main { margin-left: 0; padding: 1rem; padding-top: 72px; }
            .header h1 { font-size: 1.2rem; }
            .header { flex-direction: column; align-items: flex-start; gap: 0.75rem; }
            .header-actions { width: 100%; }
            .header-actions .btn { flex: 1; justify-content: center; }
            .stats-grid { grid-template-columns: 1fr 1fr; gap: 0.75rem; }
            .stat-card { padding: 1rem; }
            .stat-card .stat-value { font-size: 1.2rem; }
            .stat-card .stat-icon { width: 36px; height: 36px; }
            .stat-card .stat-icon span { font-size: 18px; }
            .content-grid { grid-template-columns: 1fr; }
            .test-controls { flex-direction: column; }
            .test-controls input { width: 100%; }
            .test-controls .btn { width: 100%; justify-content: center; }
            table { font-size: 0.8rem; }
            th, td { padding: 0.5rem 0.4rem; }
            .panel { padding: 1rem; }
        }

        @media (max-width: 480px) {
            .stats-grid { grid-template-columns: 1fr; }
            .main { padding: 0.75rem; padding-top: 68px; }
            .rc-meta { flex-direction: column; gap: 0.25rem; }
        }

        /* Panels */
        .panel { background: white; border-radius: 14px; border: 1px solid #e2e8f0; padding: 1.5rem; }
        .panel-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.25rem; }
        .panel-header h3 { font-size: 1rem; font-weight: 600; color: #1e293b; }
        .panel-header .view-all { font-size: 0.8rem; color: #10b981; text-decoration: none; font-weight: 500; cursor: pointer; }

        /* Table */
        .table-wrap { overflow-x: auto; -webkit-overflow-scrolling: touch; }
        table { width: 100%; border-collapse: collapse; min-width: 400px; }
        th { text-align: left; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; color: #94a3b8; padding: 0.6rem 0; border-bottom: 1px solid #f1f5f9; font-weight: 500; }
        td { padding: 0.75rem 0; border-bottom: 1px solid #f1f5f9; font-size: 0.85rem; color: #475569; vertical-align: middle; }
        .badge { display: inline-block; padding: 0.2rem 0.6rem; border-radius: 9999px; font-size: 0.7rem; font-weight: 600; }
        .badge-success { background: #d1fae5; color: #065f46; }
        .badge-info { background: #dbeafe; color: #1e40af; }
        .badge-warning { background: #fef3c7; color: #92400e; }

        /* Source Budget Panel */
        .source-item { margin-bottom: 1rem; }
        .source-item .source-header { display: flex; justify-content: space-between; font-size: 0.85rem; margin-bottom: 0.4rem; }
        .source-item .source-name { color: #475569; font-weight: 500; }
        .source-item .source-count { color: #64748b; }
        .source-item .progress-bar { height: 8px; background: #f1f5f9; border-radius: 4px; overflow: hidden; }
        .source-item .progress-fill { height: 100%; border-radius: 4px; transition: width 0.3s; }
        .source-item .progress-fill.green { background: #10b981; }
        .source-item .progress-fill.blue { background: #3b82f6; }
        .source-item .progress-fill.orange { background: #f59e0b; }

        /* Test Panel */
        .test-section { margin-bottom: 2rem; }
        .test-controls { display: flex; gap: 0.75rem; flex-wrap: wrap; margin-bottom: 1rem; }
        .test-controls input { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 0.55rem 0.75rem; color: #1e293b; font-size: 0.85rem; width: 280px; }
        .test-controls input::placeholder { color: #94a3b8; }
        .test-controls input:focus { outline: none; border-color: #10b981; box-shadow: 0 0 0 3px rgba(16,185,129,0.1); }

        /* Results */
        .results-container { display: none; max-height: 600px; overflow-y: auto; }
        .result-card { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px; padding: 1.25rem; margin-bottom: 0.75rem; }
        .result-card .rc-title { font-weight: 600; color: #1e293b; font-size: 0.95rem; }
        .result-card .rc-company { color: #64748b; font-size: 0.85rem; margin-top: 0.15rem; }
        .result-card .rc-meta { display: flex; gap: 1rem; margin-top: 0.5rem; font-size: 0.8rem; color: #94a3b8; flex-wrap: wrap; }
        .result-card .rc-tweet { background: white; border: 1px solid #e2e8f0; border-radius: 8px; padding: 0.75rem; margin-top: 0.75rem; font-size: 0.82rem; white-space: pre-wrap; color: #334155; line-height: 1.5; }
        .result-card .rc-chars { text-align: right; font-size: 0.7rem; color: #94a3b8; margin-top: 0.25rem; }

        /* Logs */
        .log-box { background: #1e293b; border-radius: 8px; padding: 1rem; font-family: 'JetBrains Mono', monospace; font-size: 0.75rem; max-height: 250px; overflow-y: auto; white-space: pre-wrap; color: #94a3b8; line-height: 1.6; }

        /* Spinner */
        .spinner { display: inline-block; width: 14px; height: 14px; border: 2px solid #e2e8f0; border-top-color: #10b981; border-radius: 50%; animation: spin 0.6s linear infinite; }
        @keyframes spin { to { transform: rotate(360deg); } }
        .status-text { font-size: 0.85rem; color: #64748b; margin-top: 0.5rem; }
        .error-box { background: #fef2f2; border: 1px solid #fecaca; border-radius: 8px; padding: 1rem; color: #991b1b; font-size: 0.85rem; }
    </style>
</head>
<body>
    <!-- Mobile Header -->
    <div class="mobile-header">
        <button class="hamburger" onclick="toggleSidebar()"><span class="material-icons-outlined">menu</span></button>
        <div class="sidebar-brand" style="margin:0; padding:0;">
            <div class="icon" style="width:30px;height:30px;"><span class="material-icons-outlined" style="font-size:16px;">smart_toy</span></div>
            <h2 style="font-size:1rem;">JobBot</h2>
        </div>
    </div>
    <div class="overlay" id="overlay" onclick="toggleSidebar()"></div>

    <!-- Sidebar -->
    <aside class="sidebar" id="sidebar">
        <div class="sidebar-brand">
            <div class="icon"><span class="material-icons-outlined" style="font-size:20px;">smart_toy</span></div>
            <h2>JobBot</h2>
        </div>
        <div class="sidebar-section">Main Menu</div>
        <ul class="sidebar-nav">
            <li><a href="#" class="active"><span class="material-icons-outlined nav-icon">dashboard</span> Dashboard</a></li>
            <li><a href="#test-section"><span class="material-icons-outlined nav-icon">science</span> Test Scrape</a></li>
            <li><a href="#posts-section"><span class="material-icons-outlined nav-icon">article</span> Posts</a></li>
            <li><a href="#logs-section"><span class="material-icons-outlined nav-icon">terminal</span> Logs</a></li>
        </ul>
        <div class="sidebar-section">Settings</div>
        <ul class="sidebar-nav">
            <li><a href="/api/health"><span class="material-icons-outlined nav-icon">monitor_heart</span> Health Check</a></li>
        </ul>
    </aside>

    <!-- Main Content -->
    <main class="main">
        <div class="header">
            <div>
                <h1>Dashboard</h1>
                <p>Monitor your job posting bot activity.</p>
            </div>
            <div class="header-actions">
                <button class="btn btn-outline" onclick="location.reload()">↻ Refresh</button>
                <button class="btn btn-primary" onclick="testScrape('all')">+ Test Scrape</button>
            </div>
        </div>

        <!-- Stats -->
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-icon green"><span class="material-icons-outlined">send</span></div>
                <div class="stat-info">
                    <div class="stat-label">Total Posted</div>
                    <div class="stat-value">{{ total_posted }}</div>
                    <div class="stat-change">All time</div>
                </div>
            </div>
            <div class="stat-card">
                <div class="stat-icon blue"><span class="material-icons-outlined">schedule</span></div>
                <div class="stat-info">
                    <div class="stat-label">Last Post</div>
                    <div class="stat-value" style="font-size:1rem;">{{ last_post_time or 'Never' }}</div>
                </div>
            </div>
            <div class="stat-card">
                <div class="stat-icon orange"><span class="material-icons-outlined">storage</span></div>
                <div class="stat-info">
                    <div class="stat-label">Database</div>
                    <div class="stat-value">{{ db_size }}</div>
                    <div class="stat-change">{{ status }}</div>
                </div>
            </div>
            <div class="stat-card">
                <div class="stat-icon purple"><span class="material-icons-outlined">power_settings_new</span></div>
                <div class="stat-info">
                    <div class="stat-label">Bot Status</div>
                    <div class="stat-value" style="color: {{ '#10b981' if status == 'Online' else '#ef4444' }}">{{ status }}</div>
                </div>
            </div>
        </div>

        <!-- Content Grid -->
        <div class="content-grid">
            <!-- Recent Posts Table -->
            <div class="panel" id="posts-section">
                <div class="panel-header">
                    <h3>Recent Posts</h3>
                    <span class="view-all">Last 20</span>
                </div>
                <div class="table-wrap">
                <table>
                    <thead>
                        <tr>
                            <th>Job ID</th>
                            <th>Tweet</th>
                            <th>Posted</th>
                            <th>Status</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for row in recent_posts %}
                        <tr>
                            <td><code style="font-size:0.75rem;">{{ row.job_id[:8] }}…</code></td>
                            <td><a href="https://x.com/i/status/{{ row.tweet_id }}" target="_blank" style="color:#3b82f6; text-decoration:none;">{{ row.tweet_id }}</a></td>
                            <td>{{ row.posted_at[:16] }}</td>
                            <td><span class="badge badge-success">Posted</span></td>
                        </tr>
                        {% endfor %}
                        {% if not recent_posts %}
                        <tr><td colspan="4" style="text-align:center; color:#94a3b8; padding:2rem;">No posts yet — run the bot to start posting</td></tr>
                        {% endif %}
                    </tbody>
                </table>
                </div>
            </div>

            <!-- Source Stats -->
            <div class="panel">
                <div class="panel-header">
                    <h3>Sources</h3>
                </div>
                <div class="source-item">
                    <div class="source-header">
                        <span class="source-name">Remotive</span>
                        <span class="source-count">5 / 10</span>
                    </div>
                    <div class="progress-bar"><div class="progress-fill green" style="width:50%"></div></div>
                </div>
                <div class="source-item">
                    <div class="source-header">
                        <span class="source-name">Jobicy</span>
                        <span class="source-count">5 / 10</span>
                    </div>
                    <div class="progress-bar"><div class="progress-fill blue" style="width:50%"></div></div>
                </div>
                <div class="source-item">
                    <div class="source-header">
                        <span class="source-name">Indeed (Playwright)</span>
                        <span class="source-count">Blocked</span>
                    </div>
                    <div class="progress-bar"><div class="progress-fill orange" style="width:0%"></div></div>
                </div>
                <div class="source-item">
                    <div class="source-header">
                        <span class="source-name">Glints (Playwright)</span>
                        <span class="source-count">Blocked</span>
                    </div>
                    <div class="progress-bar"><div class="progress-fill orange" style="width:0%"></div></div>
                </div>
                <div style="margin-top:1.5rem; padding-top:1rem; border-top:1px solid #f1f5f9;">
                    <div class="stat-label">POSTING FORMAT</div>
                    <select id="post-format" onchange="updateFormat(this.value)" style="margin-top:0.5rem; padding:0.4rem 0.75rem; border:1px solid #e2e8f0; border-radius:8px; font-size:0.85rem; font-weight:600; color:#1e293b; background:white; cursor:pointer;">
                        <option value="summary" {{ 'selected' if post_format == 'summary' else '' }}>📢 Summary (AI)</option>
                        <option value="raw" {{ 'selected' if post_format == 'raw' else '' }}>📝 Raw Detail</option>
                    </select>
                    <button class="btn btn-outline" onclick="testGroq()" style="margin-top:0.5rem; width:100%; justify-content:center; font-size:0.8rem;">
                        <span class="material-icons-outlined" style="font-size:14px;">psychology</span> Test Groq API
                    </button>
                    <div id="groq-status" style="font-size:0.75rem; margin-top:0.4rem; color:#64748b;"></div>
                </div>
            </div>
        </div>

        <!-- Test Scraping Section -->
        <div class="panel test-section" id="test-section">
            <div class="panel-header">
                <h3><span class="material-icons-outlined" style="font-size:18px; vertical-align:middle; margin-right:6px;">science</span>Test Scraping</h3>
            </div>
            <div class="test-controls">
                <input type="text" id="indeed-url" placeholder="Indeed URL (optional)" />
                <input type="text" id="glints-url" placeholder="Glints URL (optional)" />
            </div>
            <div class="test-controls">
                <button class="btn btn-primary" id="btn-test-all" onclick="testScrape('all')">Test All Sources</button>
                <button class="btn btn-outline" onclick="testScrape('indeed')">Test Indeed</button>
                <button class="btn btn-outline" onclick="testScrape('glints')">Test Glints</button>
                <button class="btn btn-outline" onclick="testFormat()">Test Format</button>
            </div>
            <div id="test-status" class="status-text"></div>
            <div class="results-container" id="results-box"></div>
        </div>

        <!-- Logs -->
        <div class="panel" id="logs-section">
            <div class="panel-header">
                <h3><span class="material-icons-outlined" style="font-size:18px; vertical-align:middle; margin-right:6px;">terminal</span>Recent Logs</h3>
            </div>
            <div class="log-box">{{ logs }}</div>
        </div>
    </main>

    <script>
    async function testScrape(source) {
        const statusEl = document.getElementById('test-status');
        const resultsEl = document.getElementById('results-box');
        const indeedUrl = document.getElementById('indeed-url').value;
        const glintsUrl = document.getElementById('glints-url').value;

        statusEl.innerHTML = '<span class="spinner"></span> Fetching ' + source + ' listings...';
        resultsEl.style.display = 'none';
        document.querySelectorAll('.test-section .btn').forEach(b => b.disabled = true);

        try {
            const params = new URLSearchParams();
            params.set('source', source);
            if (indeedUrl) params.set('indeed_url', indeedUrl);
            if (glintsUrl) params.set('glints_url', glintsUrl);

            const resp = await fetch('/api/test-scrape?' + params.toString());
            const data = await resp.json();

            if (data.error) {
                statusEl.innerHTML = '';
                resultsEl.style.display = 'block';
                resultsEl.innerHTML = '<div class="error-box">❌ ' + data.error + '</div>';
            } else {
                statusEl.innerHTML = '✅ Found ' + data.listings.length + ' listing(s) in ' + data.elapsed + 's';
                resultsEl.style.display = 'block';
                resultsEl.innerHTML = data.listings.map(l => `
                    <div class="result-card">
                        <div class="rc-title">${l.title}</div>
                        <div class="rc-company">${l.company}</div>
                        <div class="rc-meta">
                            <span><span class="material-icons-outlined" style="font-size:14px;vertical-align:middle;">location_on</span> ${l.location}</span>
                            ${l.salary ? '<span><span class="material-icons-outlined" style="font-size:14px;vertical-align:middle;">payments</span> ' + l.salary + '</span>' : ''}
                            <span class="badge badge-info">${l.source}</span>
                        </div>
                        <div class="rc-tweet">${l.tweet_preview || ''}</div>
                        <div class="rc-chars">${l.tweet_length} chars (rich) · ${l.compact_length}/280 (compact)</div>
                    </div>
                `).join('') || '<p style="color:#94a3b8; text-align:center; padding:1rem;">No listings found</p>';
            }
        } catch (err) {
            statusEl.innerHTML = '';
            resultsEl.style.display = 'block';
            resultsEl.innerHTML = '<div class="error-box">❌ Network error: ' + err.message + '</div>';
        } finally {
            document.querySelectorAll('.test-section .btn').forEach(b => b.disabled = false);
        }
    }

    async function testFormat() {
        const statusEl = document.getElementById('test-status');
        const resultsEl = document.getElementById('results-box');
        statusEl.innerHTML = '<span class="spinner"></span> Testing format...';
        resultsEl.style.display = 'none';
        try {
            const resp = await fetch('/api/test-format');
            const data = await resp.json();
            statusEl.innerHTML = '✅ Format test done — ' + data.results.length + ' samples';
            resultsEl.style.display = 'block';
            resultsEl.innerHTML = data.results.map(r => `
                <div class="result-card">
                    <div class="rc-title">${r.title} <span class="badge badge-info">${r.source}</span></div>
                    <div class="rc-tweet">${r.tweet}</div>
                    <div class="rc-chars">${r.length}/280 chars ${r.length <= 280 ? '✅' : '❌ OVER'}</div>
                </div>
            `).join('');
        } catch (err) {
            statusEl.innerHTML = '';
            resultsEl.style.display = 'block';
            resultsEl.innerHTML = '<div class="error-box">❌ ' + err.message + '</div>';
        }
    }
    function toggleSidebar() {
        document.getElementById('sidebar').classList.toggle('open');
        document.getElementById('overlay').classList.toggle('open');
    }

    async function updateFormat(fmt) {
        try {
            await fetch('/api/format', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({format: fmt})
            });
        } catch(e) { console.error(e); }
    }

    async function testGroq() {
        const el = document.getElementById('groq-status');
        el.innerHTML = '<span class="spinner"></span> Testing...';
        el.style.color = '#64748b';
        try {
            const resp = await fetch('/api/test-groq');
            const data = await resp.json();
            if (data.success) {
                el.innerHTML = '✅ Connected (' + data.model + ') — ' + data.elapsed + 's';
                el.style.color = '#10b981';
            } else {
                let msg = '❌ ' + data.error;
                if (data.debug) msg += '<br><small style="color:#94a3b8;">' + data.debug + '</small>';
                el.innerHTML = msg;
                el.style.color = '#ef4444';
            }
        } catch(e) {
            el.innerHTML = '❌ Network error';
            el.style.color = '#ef4444';
        }
    }

    // Close sidebar on nav click (mobile)
    document.querySelectorAll('.sidebar-nav a').forEach(a => {
        a.addEventListener('click', () => {
            if (window.innerWidth <= 768) toggleSidebar();
        });
    });
    </script>
</body>
</html>
"""


def _get_db_stats() -> dict:
    """Read stats from the SQLite database."""
    if not Path(DB_PATH).exists():
        return {"total_posted": 0, "last_post_time": None, "recent_posts": [], "db_size": "0 KB"}

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.execute("SELECT COUNT(*) as cnt FROM posted_jobs")
        total = cursor.fetchone()["cnt"]

        cursor = conn.execute(
            "SELECT job_id, tweet_id, posted_at FROM posted_jobs ORDER BY posted_at DESC LIMIT 20"
        )
        recent = [dict(row) for row in cursor.fetchall()]
        last_post = recent[0]["posted_at"] if recent else None

        db_size_bytes = Path(DB_PATH).stat().st_size
        if db_size_bytes < 1024:
            db_size = f"{db_size_bytes} B"
        elif db_size_bytes < 1024 * 1024:
            db_size = f"{db_size_bytes // 1024} KB"
        else:
            db_size = f"{db_size_bytes // (1024 * 1024)} MB"

        return {"total_posted": total, "last_post_time": last_post, "recent_posts": recent, "db_size": db_size}
    finally:
        conn.close()


def _get_recent_logs(lines: int = 50) -> str:
    if not Path(LOG_PATH).exists():
        return "No log file found. Bot may not have run yet."
    try:
        with open(LOG_PATH, "r") as f:
            return "".join(f.readlines()[-lines:])
    except Exception as e:
        return f"Error reading logs: {e}"


@app.route("/")
def index():
    stats = _get_db_stats()
    logs = _get_recent_logs()
    status = "Online" if Path(DB_PATH).exists() else "Offline"
    format_file = Path("post_format.txt")
    post_format = format_file.read_text().strip() if format_file.exists() else os.environ.get("POST_FORMAT", "summary")
    return render_template_string(
        DASHBOARD_HTML,
        status=status,
        total_posted=stats["total_posted"],
        last_post_time=stats["last_post_time"],
        db_size=stats["db_size"],
        recent_posts=stats["recent_posts"],
        logs=logs,
        post_format=post_format,
    )


@app.route("/api/stats")
def api_stats():
    return jsonify(_get_db_stats())


@app.route("/api/health")
def api_health():
    return jsonify({"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()})


@app.route("/api/schedule")
def api_schedule():
    from scheduler import get_schedule_summary
    return jsonify(get_schedule_summary())


@app.route("/api/format", methods=["GET", "POST"])
def api_format():
    """Get or set the posting format."""
    format_file = Path("post_format.txt")
    if request.method == "POST":
        data = request.get_json() or {}
        fmt = data.get("format", "summary")
        if fmt in ("raw", "summary"):
            format_file.write_text(fmt)
            return jsonify({"format": fmt, "status": "updated"})
        return jsonify({"error": "Invalid format"}), 400
    else:
        fmt = format_file.read_text().strip() if format_file.exists() else os.environ.get("POST_FORMAT", "summary")
        return jsonify({"format": fmt})


@app.route("/api/test-groq")
def api_test_groq():
    """Test Groq API connection."""
    import time as _time
    start = _time.time()
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        return jsonify({"success": False, "error": "GROQ_API_KEY not set in environment", "elapsed": 0,
                        "debug": f"Env keys containing 'GROQ': {[k for k in os.environ if 'GROQ' in k.upper()]}"})

    # Show masked key for debugging
    masked = api_key[:4] + "..." + api_key[-4:] if len(api_key) > 8 else "***"
    key_len = len(api_key)

    try:
        resp = httpx.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "llama-3.1-8b-instant",
                "messages": [{"role": "user", "content": "Say 'OK' if you can read this."}],
                "max_tokens": 10,
            },
            timeout=15,
        )
        elapsed = round(_time.time() - start, 2)

        if resp.status_code == 200:
            data = resp.json()
            reply = data["choices"][0]["message"]["content"].strip()
            model = data.get("model", "unknown")
            return jsonify({"success": True, "reply": reply, "model": model, "elapsed": elapsed})
        else:
            return jsonify({"success": False, "error": f"HTTP {resp.status_code}: {resp.text[:200]}",
                            "elapsed": elapsed, "debug": f"Key: {masked} (len={key_len})"})
    except Exception as e:
        elapsed = round(_time.time() - start, 2)
        return jsonify({"success": False, "error": str(e), "elapsed": elapsed})


@app.route("/api/test-scrape")
def api_test_scrape():
    import time as _time
    source = request.args.get("source", "all")
    indeed_url = request.args.get("indeed_url", "https://id.indeed.com/jobs?q=remote+work+from+home&l=Indonesia")
    glints_url = request.args.get("glints_url", "https://glints.com/id/opportunities/jobs/explore?keyword=remote&country=ID&workArrangement=REMOTE")
    start = _time.time()

    try:
        from scraper.httpx_scraper import IndeedHTTPSource, GlintsHTTPSource, RemotiveSource, JobicySource
        from scraper import fetch_all
        from formatter import format_tweet, format_rich_post, format_thread

        sources_list = []
        if source in ("indeed", "all"):
            primary = IndeedHTTPSource(search_url=indeed_url, inter_request_delay_seconds=1)
            fallback = RemotiveSource(category="software-dev", inter_request_delay_seconds=1)
            sources_list.append((primary, fallback))
        if source in ("glints", "all"):
            primary = GlintsHTTPSource(search_url=glints_url, inter_request_delay_seconds=1)
            fallback = JobicySource(tag="developer", inter_request_delay_seconds=1)
            sources_list.append((primary, fallback))

        listings = fetch_all(sources_list, limit_per_source=5)
        results = []
        for listing in listings:
            try:
                tweet_compact = format_tweet(listing)
                tweet_rich = format_rich_post(listing)
                thread = format_thread(listing)
            except Exception:
                tweet_compact = tweet_rich = None
                thread = []
            results.append({
                "job_id": listing.job_id, "title": listing.title,
                "company": listing.company, "location": listing.location,
                "salary": listing.salary, "url": listing.url, "source": listing.source,
                "tweet_preview": tweet_rich, "tweet_length": len(tweet_rich) if tweet_rich else 0,
                "tweet_compact": tweet_compact, "compact_length": len(tweet_compact) if tweet_compact else 0,
                "thread": thread,
            })
        return jsonify({"listings": results, "elapsed": round(_time.time() - start, 2), "error": None})
    except Exception as e:
        return jsonify({"listings": [], "elapsed": round(_time.time() - start, 2), "error": f"{type(e).__name__}: {e}\n{traceback.format_exc()}"})


@app.route("/api/test-format")
def api_test_format():
    from models import JobListing
    from formatter import format_tweet
    samples = [
        JobListing(job_id="a"*16, title="Backend Developer", company="Tokopedia", location="Remote", salary="Rp 15-25jt/bulan", url="https://example.com/job/1", source="indeed"),
        JobListing(job_id="b"*16, title="Senior Full Stack Engineer - React & Node.js", company="Gojek", location="Jakarta (WFH)", salary=None, url="https://example.com/job/2", source="glints"),
        JobListing(job_id="c"*16, title="A"*200+" Very Long Title", company="PT Startup", location="Remote", salary="Rp 30-50jt", url="https://example.com/job/3", source="indeed"),
        JobListing(job_id="d"*16, title="🚀 Pengembang Perangkat Lunak Senior", company="Bukalapak", location="Remote", salary=None, url="https://example.com/job/4", source="glints"),
    ]
    results = [{"title": l.title[:50]+("..." if len(l.title)>50 else ""), "source": l.source, "tweet": format_tweet(l), "length": len(format_tweet(l))} for l in samples]
    return jsonify({"results": results})


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s",
                        handlers=[logging.StreamHandler(), logging.FileHandler("bot.log")])
    port = int(os.environ.get("DASHBOARD_PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
