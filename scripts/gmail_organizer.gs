/**
 * Gmail Organization Suite - Google Apps Script
 *
 * Features:
 *   1. Auto-label emails by sender, domain, and keywords
 *   2. Archive old inbox emails past a configurable age
 *   3. Newsletter detection, labeling, and optional auto-archive
 *   4. Daily digest email summarizing inbox activity
 *
 * Setup:
 *   1. Go to https://script.google.com and create a new project
 *   2. Paste this entire file into Code.gs
 *   3. Run `setup()` once to create labels and time-based triggers
 *   4. Customize the CONFIG object below to match your preferences
 *   5. Run `organizeAll()` manually for the first pass, then triggers handle the rest
 */

// ============================================================
// CONFIGURATION — edit this section to match your preferences
// ============================================================
const CONFIG = {
  // --- Auto-Label Rules ---
  // Each rule: { label, match } where match has: from, domain, subject, or body (regex strings)
  labelRules: [
    { label: "Finance",      match: { domain: "(bank|chase|fidelity|schwab|vanguard|paypal|venmo|coinbase)\\.com" } },
    { label: "Shopping",     match: { domain: "(amazon|ebay|etsy|walmart|target|bestbuy)\\.com" } },
    { label: "Travel",       match: { domain: "(airline|united|delta|american|southwest|airbnb|booking|expedia)\\.com" } },
    { label: "Social",       match: { domain: "(facebook|twitter|x|linkedin|instagram|reddit|discord)\\.com" } },
    { label: "Dev/GitHub",   match: { domain: "(github|gitlab|bitbucket|stackoverflow|npmjs)\\.com" } },
    { label: "Receipts",     match: { subject: "(receipt|order confirm|invoice|payment received)" } },
    { label: "Alerts",       match: { subject: "(alert|security|unusual sign-in|verify your)" } },
    // Add your own rules here:
    // { label: "Work", match: { domain: "yourcompany\\.com" } },
  ],

  // --- Archive Settings ---
  archiveAfterDays: 30,          // Archive inbox emails older than this many days
  archiveMaxPerRun: 100,         // Max threads to archive per execution (avoid timeout)
  archiveExcludeStarred: true,   // Never archive starred emails
  archiveExcludeLabels: ["Action Required"],  // Never archive emails with these labels

  // --- Newsletter Settings ---
  newsletterLabel: "Newsletters",
  newsletterAutoArchive: true,   // Auto-archive detected newsletters (still labeled)
  newsletterIndicators: [        // Patterns that identify newsletters
    "unsubscribe",
    "email preferences",
    "manage subscriptions",
    "opt out",
    "notification settings",
    "view in browser",
    "view as web page",
  ],

  // --- Daily Digest ---
  digestEnabled: true,
  digestHour: 8,                 // Hour (0-23) to send digest (in your Gmail timezone)
  digestRecipient: "me",         // "me" sends to yourself

  // --- General ---
  maxThreadsPerSearch: 50,       // Limit per search to avoid execution timeouts
  dryRun: false,                 // Set true to log actions without making changes
};


// ============================================================
// SETUP — run once to create labels and triggers
// ============================================================

function setup() {
  createLabels_();
  createTriggers_();
  Logger.log("Setup complete. Labels created and triggers installed.");
  Logger.log("Run organizeAll() for an initial pass, then triggers will handle the rest.");
}

function createLabels_() {
  const needed = new Set();

  // Collect labels from rules
  CONFIG.labelRules.forEach(r => needed.add(r.label));
  needed.add(CONFIG.newsletterLabel);
  CONFIG.archiveExcludeLabels.forEach(l => needed.add(l));

  // Get existing labels
  const existing = new Set(GmailApp.getUserLabels().map(l => l.getName()));

  needed.forEach(name => {
    if (!existing.has(name)) {
      GmailApp.createLabel(name);
      Logger.log(`Created label: ${name}`);
    }
  });
}

function createTriggers_() {
  // Remove existing triggers for this project to avoid duplicates
  ScriptApp.getProjectTriggers().forEach(t => ScriptApp.deleteTrigger(t));

  // Auto-label + newsletter detection — every 15 minutes
  ScriptApp.newTrigger("autoLabelInbox")
    .timeBased()
    .everyMinutes(15)
    .create();

  // Archive old emails — daily at 2 AM
  ScriptApp.newTrigger("archiveOldEmails")
    .timeBased()
    .atHour(2)
    .everyDays(1)
    .create();

  // Daily digest — at configured hour
  if (CONFIG.digestEnabled) {
    ScriptApp.newTrigger("sendDailyDigest")
      .timeBased()
      .atHour(CONFIG.digestHour)
      .everyDays(1)
      .create();
  }

  Logger.log("Triggers created: autoLabelInbox (15min), archiveOldEmails (daily 2AM)" +
    (CONFIG.digestEnabled ? `, sendDailyDigest (daily ${CONFIG.digestHour}:00)` : ""));
}


// ============================================================
// 1. AUTO-LABEL
// ============================================================

function autoLabelInbox() {
  const threads = GmailApp.getInboxThreads(0, CONFIG.maxThreadsPerSearch);
  let labeled = 0;

  threads.forEach(thread => {
    const messages = thread.getMessages();
    const firstMsg = messages[0];
    const from = firstMsg.getFrom().toLowerCase();
    const subject = firstMsg.getSubject().toLowerCase();
    const body = firstMsg.getPlainBody().substring(0, 3000).toLowerCase(); // first 3k chars for perf

    CONFIG.labelRules.forEach(rule => {
      if (matchesRule_(from, subject, body, rule.match)) {
        applyLabel_(thread, rule.label);
        labeled++;
      }
    });

    // Newsletter detection
    if (isNewsletter_(from, subject, body)) {
      applyLabel_(thread, CONFIG.newsletterLabel);
      if (CONFIG.newsletterAutoArchive && !CONFIG.dryRun) {
        thread.moveToArchive();
      }
      labeled++;
    }
  });

  Logger.log(`Auto-label complete. Processed ${threads.length} threads, applied ${labeled} labels.`);
}

function matchesRule_(from, subject, body, match) {
  if (match.from && new RegExp(match.from, "i").test(from)) return true;
  if (match.domain && new RegExp(match.domain, "i").test(from)) return true;
  if (match.subject && new RegExp(match.subject, "i").test(subject)) return true;
  if (match.body && new RegExp(match.body, "i").test(body)) return true;
  return false;
}

function isNewsletter_(from, subject, body) {
  const combined = body + " " + from;
  let hits = 0;
  CONFIG.newsletterIndicators.forEach(indicator => {
    if (combined.includes(indicator.toLowerCase())) hits++;
  });
  // Require at least 2 indicators to avoid false positives
  return hits >= 2;
}

function applyLabel_(thread, labelName) {
  if (CONFIG.dryRun) {
    Logger.log(`[DRY RUN] Would label "${thread.getFirstMessageSubject()}" as "${labelName}"`);
    return;
  }
  const label = GmailApp.getUserLabelByName(labelName);
  if (label) {
    label.addToThread(thread);
  }
}


// ============================================================
// 2. ARCHIVE OLD EMAILS
// ============================================================

function archiveOldEmails() {
  const cutoffDate = new Date();
  cutoffDate.setDate(cutoffDate.getDate() - CONFIG.archiveAfterDays);
  const dateStr = Utilities.formatDate(cutoffDate, Session.getScriptTimeZone(), "yyyy/MM/dd");

  let query = `in:inbox before:${dateStr}`;
  if (CONFIG.archiveExcludeStarred) {
    query += " -is:starred";
  }
  CONFIG.archiveExcludeLabels.forEach(label => {
    query += ` -label:${label.toLowerCase().replace(/ /g, "-")}`;
  });

  const threads = GmailApp.search(query, 0, CONFIG.archiveMaxPerRun);
  let archived = 0;

  threads.forEach(thread => {
    if (CONFIG.dryRun) {
      Logger.log(`[DRY RUN] Would archive: "${thread.getFirstMessageSubject()}" (${thread.getLastMessageDate()})`);
    } else {
      thread.moveToArchive();
    }
    archived++;
  });

  Logger.log(`Archive complete. ${CONFIG.dryRun ? "Would archive" : "Archived"} ${archived} threads older than ${CONFIG.archiveAfterDays} days.`);
}


// ============================================================
// 3. NEWSLETTER CLEANUP (standalone run)
// ============================================================

function cleanupNewsletters() {
  const query = "in:inbox (unsubscribe OR \"email preferences\" OR \"manage subscriptions\")";
  const threads = GmailApp.search(query, 0, CONFIG.maxThreadsPerSearch);
  let count = 0;

  threads.forEach(thread => {
    const body = thread.getMessages()[0].getPlainBody().substring(0, 3000).toLowerCase();
    const from = thread.getMessages()[0].getFrom().toLowerCase();

    if (isNewsletter_(from, "", body)) {
      applyLabel_(thread, CONFIG.newsletterLabel);
      if (CONFIG.newsletterAutoArchive && !CONFIG.dryRun) {
        thread.moveToArchive();
      }
      count++;
    }
  });

  Logger.log(`Newsletter cleanup: found and processed ${count} newsletter threads.`);
}


// ============================================================
// 4. DAILY DIGEST
// ============================================================

function sendDailyDigest() {
  if (!CONFIG.digestEnabled) return;

  const now = new Date();
  const yesterday = new Date(now.getTime() - 24 * 60 * 60 * 1000);
  const dateStr = Utilities.formatDate(yesterday, Session.getScriptTimeZone(), "yyyy/MM/dd");

  // Gather stats
  const inboxCount = GmailApp.getInboxThreads().length;
  const unreadCount = GmailApp.getInboxUnreadCount();
  const newQuery = `in:inbox after:${dateStr}`;
  const newThreads = GmailApp.search(newQuery, 0, 200);

  // Count by label
  const labelCounts = {};
  CONFIG.labelRules.forEach(rule => {
    const label = GmailApp.getUserLabelByName(rule.label);
    if (label) {
      const labelNewQuery = `label:${rule.label.toLowerCase().replace(/ /g, "-")} after:${dateStr}`;
      const labelThreads = GmailApp.search(labelNewQuery, 0, 200);
      if (labelThreads.length > 0) {
        labelCounts[rule.label] = labelThreads.length;
      }
    }
  });

  // Newsletter count
  const nlLabel = GmailApp.getUserLabelByName(CONFIG.newsletterLabel);
  if (nlLabel) {
    const nlQuery = `label:${CONFIG.newsletterLabel.toLowerCase()} after:${dateStr}`;
    const nlThreads = GmailApp.search(nlQuery, 0, 200);
    if (nlThreads.length > 0) {
      labelCounts[CONFIG.newsletterLabel] = nlThreads.length;
    }
  }

  // Top senders
  const senderMap = {};
  newThreads.forEach(thread => {
    const from = thread.getMessages()[0].getFrom();
    const name = from.replace(/<.*>/, "").trim() || from;
    senderMap[name] = (senderMap[name] || 0) + 1;
  });
  const topSenders = Object.entries(senderMap)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 10);

  // Build digest HTML
  const digestDate = Utilities.formatDate(now, Session.getScriptTimeZone(), "EEEE, MMMM d, yyyy");
  let html = `
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto;">
      <h2 style="color: #1a73e8; border-bottom: 2px solid #1a73e8; padding-bottom: 8px;">
        Gmail Daily Digest — ${digestDate}
      </h2>

      <div style="background: #f8f9fa; padding: 16px; border-radius: 8px; margin: 16px 0;">
        <h3 style="margin-top: 0;">Inbox Snapshot</h3>
        <table style="width: 100%; border-collapse: collapse;">
          <tr><td style="padding: 4px 8px;">Total inbox threads</td><td style="text-align: right; font-weight: bold;">${inboxCount}</td></tr>
          <tr><td style="padding: 4px 8px;">Unread</td><td style="text-align: right; font-weight: bold; color: #d93025;">${unreadCount}</td></tr>
          <tr><td style="padding: 4px 8px;">New in last 24h</td><td style="text-align: right; font-weight: bold;">${newThreads.length}</td></tr>
        </table>
      </div>`;

  if (Object.keys(labelCounts).length > 0) {
    html += `
      <div style="background: #f8f9fa; padding: 16px; border-radius: 8px; margin: 16px 0;">
        <h3 style="margin-top: 0;">By Category (last 24h)</h3>
        <table style="width: 100%; border-collapse: collapse;">`;
    Object.entries(labelCounts)
      .sort((a, b) => b[1] - a[1])
      .forEach(([label, count]) => {
        html += `<tr><td style="padding: 4px 8px;">${label}</td><td style="text-align: right; font-weight: bold;">${count}</td></tr>`;
      });
    html += `</table></div>`;
  }

  if (topSenders.length > 0) {
    html += `
      <div style="background: #f8f9fa; padding: 16px; border-radius: 8px; margin: 16px 0;">
        <h3 style="margin-top: 0;">Top Senders (last 24h)</h3>
        <table style="width: 100%; border-collapse: collapse;">`;
    topSenders.forEach(([sender, count]) => {
      html += `<tr><td style="padding: 4px 8px;">${sender}</td><td style="text-align: right; font-weight: bold;">${count}</td></tr>`;
    });
    html += `</table></div>`;
  }

  html += `
      <p style="color: #5f6368; font-size: 12px; margin-top: 24px;">
        Generated by Gmail Organization Suite • Auto-label runs every 15 min • Archive runs daily at 2 AM
      </p>
    </div>`;

  if (CONFIG.dryRun) {
    Logger.log("[DRY RUN] Would send digest email");
    Logger.log(html);
  } else {
    GmailApp.sendEmail(
      CONFIG.digestRecipient,
      `Gmail Digest: ${unreadCount} unread, ${newThreads.length} new — ${digestDate}`,
      `Inbox: ${inboxCount} threads, ${unreadCount} unread, ${newThreads.length} new in 24h.`,
      { htmlBody: html }
    );
  }

  Logger.log(`Daily digest sent. ${inboxCount} inbox threads, ${unreadCount} unread, ${newThreads.length} new.`);
}


// ============================================================
// MASTER FUNCTION — runs everything at once
// ============================================================

function organizeAll() {
  Logger.log("=== Starting full Gmail organization ===");
  autoLabelInbox();
  cleanupNewsletters();
  archiveOldEmails();
  Logger.log("=== Organization complete ===");
}


// ============================================================
// UTILITIES
// ============================================================

/** List all label rules (for debugging) */
function listRules() {
  Logger.log("=== Label Rules ===");
  CONFIG.labelRules.forEach((rule, i) => {
    Logger.log(`${i + 1}. "${rule.label}" — ${JSON.stringify(rule.match)}`);
  });
  Logger.log(`Newsletter label: "${CONFIG.newsletterLabel}"`);
  Logger.log(`Archive after: ${CONFIG.archiveAfterDays} days`);
  Logger.log(`Dry run: ${CONFIG.dryRun}`);
}

/** Preview what would happen without making changes */
function dryRunAll() {
  const original = CONFIG.dryRun;
  CONFIG.dryRun = true;
  organizeAll();
  CONFIG.dryRun = original;
}

/** Remove all triggers (cleanup) */
function removeTriggers() {
  ScriptApp.getProjectTriggers().forEach(t => ScriptApp.deleteTrigger(t));
  Logger.log("All triggers removed.");
}
