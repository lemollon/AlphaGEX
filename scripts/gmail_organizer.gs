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
 *   3. Run `assessMyGmail()` FIRST — sends you a full inbox audit email (read-only, changes nothing)
 *   4. Review the assessment, then customize the CONFIG object below
 *   5. Run `setup()` once to create labels and time-based triggers
 *   6. Run `dryRunAll()` to preview changes, then `organizeAll()` for the first real pass
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
// 0. FULL INBOX ASSESSMENT — BATCHED (handles 20k+ inboxes)
// ============================================================

/**
 * Batched Gmail assessment that handles any inbox size.
 * Processes as many threads as possible within the 6-min Apps Script limit,
 * saves progress, and auto-resumes via a 5-minute trigger.
 *
 * For 21,000 threads: ~4-5 runs over ~25 minutes, fully automatic.
 *
 * Just run assessMyGmail() once — it handles everything.
 * If anything gets stuck, run resetAssessment() to start over.
 */
function assessMyGmail() {
  var TIME_LIMIT_MS = 5 * 60 * 1000; // bail at 5 min to stay under 6-min limit
  var PAGE = 500;                     // threads per Gmail API fetch
  var startTime = new Date().getTime();
  var props = PropertiesService.getScriptProperties();

  // ---- Load or initialize state ----
  var state = loadAssessmentState_(props);
  var offset = state.offset;

  Logger.log("=== Assessment batch starting at offset " + offset + " ===");

  // ---- Process threads until time runs out ----
  while (true) {
    // Time check — bail if approaching limit
    if (new Date().getTime() - startTime > TIME_LIMIT_MS) {
      Logger.log("Approaching time limit. Saving progress at offset " + offset);
      break;
    }

    var batch = GmailApp.getInboxThreads(offset, PAGE);
    if (batch.length === 0) {
      // We've reached the end
      state.complete = true;
      Logger.log("All threads scanned. Total: " + offset);
      break;
    }

    for (var i = 0; i < batch.length; i++) {
      try {
        analyzeThread_(batch[i], state);
      } catch (e) {
        state.errors++;
      }
    }

    offset += batch.length;
    state.offset = offset;
    state.totalThreads = offset;

    var elapsed = ((new Date().getTime() - startTime) / 1000).toFixed(0);
    Logger.log("Scanned " + offset + " threads so far (" + elapsed + "s elapsed)");

    if (batch.length < PAGE) {
      state.complete = true;
      Logger.log("Reached end of inbox at " + offset + " threads.");
      break;
    }
  }

  state.unreadCount = GmailApp.getInboxUnreadCount();

  // ---- Save state ----
  saveAssessmentState_(props, state);

  if (state.complete) {
    // All done — build and send report, then clean up
    Logger.log("Assessment complete. Building report...");
    sendAssessmentReport_(state);
    clearAssessmentState_(props);
    removeAssessmentTrigger_();
    Logger.log("Report emailed. Assessment state cleared.");
  } else {
    // More to do — ensure auto-resume trigger exists
    ensureAssessmentTrigger_();
    Logger.log("Progress saved. " + offset + " threads processed so far. Will auto-resume in ~5 min.");
  }
}

/**
 * Reset a stuck or partial assessment and start fresh.
 */
function resetAssessment() {
  PropertiesService.getScriptProperties().deleteProperty("ASSESS_STATE");
  removeAssessmentTrigger_();
  Logger.log("Assessment state cleared. Run assessMyGmail() to start fresh.");
}

// ---- State management ----

function loadAssessmentState_(props) {
  var raw = props.getProperty("ASSESS_STATE");
  if (raw) {
    return JSON.parse(raw);
  }
  return {
    offset: 0,
    totalThreads: 0,
    unreadCount: 0,
    complete: false,
    errors: 0,
    startedAt: new Date().toISOString(),
    senderCount: {},
    domainCount: {},
    newsletterSenders: {},
    ageBuckets: { "Today": 0, "Yesterday": 0, "This week": 0, "This month": 0,
                  "1-3 months": 0, "3-6 months": 0, "6-12 months": 0, "1-2 years": 0, "2+ years": 0 },
    unreadByAge: { "Today": 0, "Yesterday": 0, "This week": 0, "This month": 0,
                   "1-3 months": 0, "3-6 months": 0, "6-12 months": 0, "1-2 years": 0, "2+ years": 0 },
    dayOfWeekCount: [0, 0, 0, 0, 0, 0, 0],
    hourCount: [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
    largeEmails: [],
    oldestDate: null,
    newestDate: null,
    totalMessages: 0
  };
}

function saveAssessmentState_(props, state) {
  // Trim large emails to top 15 before saving
  state.largeEmails.sort(function(a, b) { return b.sizeKB - a.sizeKB; });
  state.largeEmails = state.largeEmails.slice(0, 15);

  // Trim maps to stay under Properties size limit (9KB per property)
  state.senderCount = trimToTopN_(state.senderCount, 50);
  state.domainCount = trimToTopN_(state.domainCount, 50);
  state.newsletterSenders = trimToTopN_(state.newsletterSenders, 30);

  props.setProperty("ASSESS_STATE", JSON.stringify(state));
}

function clearAssessmentState_(props) {
  props.deleteProperty("ASSESS_STATE");
}

function trimToTopN_(obj, n) {
  var entries = Object.entries(obj).sort(function(a, b) { return b[1] - a[1]; });
  var result = {};
  entries.slice(0, n).forEach(function(e) { result[e[0]] = e[1]; });
  return result;
}

// ---- Thread analysis (called per thread) ----

function analyzeThread_(thread, state) {
  var messages = thread.getMessages();
  var firstMsg = messages[0];
  var lastDate = thread.getLastMessageDate();
  var from = firstMsg.getFrom();
  var subject = firstMsg.getSubject();
  var isUnread = thread.isUnread();

  state.totalMessages += messages.length;

  // Oldest / newest
  var lastDateStr = lastDate.toISOString();
  if (!state.oldestDate || lastDateStr < state.oldestDate) state.oldestDate = lastDateStr;
  if (!state.newestDate || lastDateStr > state.newestDate) state.newestDate = lastDateStr;

  // Sender
  var senderKey = from.replace(/<.*>/, "").trim() || from;
  state.senderCount[senderKey] = (state.senderCount[senderKey] || 0) + 1;

  // Domain
  var domainMatch = from.match(/@([a-zA-Z0-9.-]+)/);
  if (domainMatch) {
    var domain = domainMatch[1].toLowerCase();
    state.domainCount[domain] = (state.domainCount[domain] || 0) + 1;
  }

  // Age bucket
  var now = new Date();
  var ageDays = (now - lastDate) / 86400000;
  var bucket = ageDays < 1 ? "Today"
    : ageDays < 2 ? "Yesterday"
    : ageDays < 7 ? "This week"
    : ageDays < 30 ? "This month"
    : ageDays < 90 ? "1-3 months"
    : ageDays < 180 ? "3-6 months"
    : ageDays < 365 ? "6-12 months"
    : ageDays < 730 ? "1-2 years"
    : "2+ years";
  state.ageBuckets[bucket]++;
  if (isUnread) state.unreadByAge[bucket]++;

  // Day of week & hour
  state.dayOfWeekCount[lastDate.getDay()]++;
  state.hourCount[lastDate.getHours()]++;

  // Newsletter + large email detection (single body fetch for speed)
  try {
    var body = firstMsg.getPlainBody().substring(0, 3000).toLowerCase();
    if (isNewsletter_(from.toLowerCase(), subject.toLowerCase(), body)) {
      state.newsletterSenders[senderKey] = (state.newsletterSenders[senderKey] || 0) + 1;
    }
    // Estimate size from plain body * message count (avoids extra getBody() API calls)
    var estimatedSize = body.length * messages.length;
    if (estimatedSize > 100000) {
      state.largeEmails.push({
        subject: subject.substring(0, 60),
        from: senderKey.substring(0, 30),
        date: Utilities.formatDate(lastDate, Session.getScriptTimeZone(), "yyyy-MM-dd"),
        sizeKB: Math.round(estimatedSize / 1024)
      });
    }
  } catch (e) {
    // Skip body analysis on error
  }
}

// ---- Auto-resume trigger ----

function ensureAssessmentTrigger_() {
  var triggers = ScriptApp.getProjectTriggers();
  for (var i = 0; i < triggers.length; i++) {
    if (triggers[i].getHandlerFunction() === "assessMyGmail") return;
  }
  ScriptApp.newTrigger("assessMyGmail")
    .timeBased()
    .everyMinutes(5)
    .create();
  Logger.log("Auto-resume trigger created (every 5 min).");
}

function removeAssessmentTrigger_() {
  ScriptApp.getProjectTriggers().forEach(function(t) {
    if (t.getHandlerFunction() === "assessMyGmail") {
      ScriptApp.deleteTrigger(t);
    }
  });
  Logger.log("Assessment trigger removed.");
}

// ---- Report builder (runs once when all threads are scanned) ----

function sendAssessmentReport_(state) {
  var now = new Date();
  var reportDate = Utilities.formatDate(now, Session.getScriptTimeZone(), "EEEE, MMMM d, yyyy h:mm a");
  var startedAt = state.startedAt ? new Date(state.startedAt) : now;
  var elapsedMin = ((now - startedAt) / 60000).toFixed(1);
  var totalThreads = state.totalThreads;

  var topSenders = Object.entries(state.senderCount).sort(function(a, b) { return b[1] - a[1]; }).slice(0, 25);
  var topDomains = Object.entries(state.domainCount).sort(function(a, b) { return b[1] - a[1]; }).slice(0, 25);
  var topNewsletters = Object.entries(state.newsletterSenders).sort(function(a, b) { return b[1] - a[1]; }).slice(0, 20);
  var suggestions = generateSuggestions_(topDomains, topSenders, topNewsletters, state.ageBuckets, totalThreads);

  // Existing labels
  var existingLabels = GmailApp.getUserLabels().map(function(label) {
    return { name: label.getName(), threads: label.getThreads(0, 1).length > 0 ? label.getThreads().length : 0 };
  });
  existingLabels.sort(function(a, b) { return b.threads - a.threads; });

  var dayNames = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];

  // ---- Build HTML report ----
  var html = '<div style="font-family: -apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, sans-serif; max-width: 700px; margin: 0 auto; color: #202124;">' +
    '<h1 style="color: #1a73e8; border-bottom: 3px solid #1a73e8; padding-bottom: 10px;">Gmail Inbox Assessment Report</h1>' +
    '<p style="color: #5f6368;">Generated ' + reportDate + ' &bull; Scanned ' + totalThreads.toLocaleString() + ' threads (' + state.totalMessages.toLocaleString() + ' messages) in ' + elapsedMin + ' min (batched)' +
    (state.errors > 0 ? ' &bull; ' + state.errors + ' threads skipped due to errors' : '') + '</p>';

  // OVERVIEW
  html += '<div style="background: #e8f0fe; padding: 20px; border-radius: 8px; margin: 20px 0;">' +
    '<h2 style="margin-top: 0; color: #1a73e8;">Overview</h2>' +
    '<table style="width: 100%; border-collapse: collapse; font-size: 15px;">' +
    '<tr><td style="padding: 6px 10px;">Total inbox threads</td><td style="text-align: right; font-weight: bold; font-size: 18px;">' + totalThreads.toLocaleString() + '</td></tr>' +
    '<tr><td style="padding: 6px 10px;">Total messages</td><td style="text-align: right; font-weight: bold;">' + state.totalMessages.toLocaleString() + '</td></tr>' +
    '<tr><td style="padding: 6px 10px;">Unread</td><td style="text-align: right; font-weight: bold; color: #d93025;">' + state.unreadCount.toLocaleString() + ' (' + (totalThreads > 0 ? Math.round(state.unreadCount / totalThreads * 100) : 0) + '%)</td></tr>' +
    '<tr><td style="padding: 6px 10px;">Unique senders (top 50 tracked)</td><td style="text-align: right; font-weight: bold;">' + Object.keys(state.senderCount).length.toLocaleString() + '</td></tr>' +
    '<tr><td style="padding: 6px 10px;">Unique domains (top 50 tracked)</td><td style="text-align: right; font-weight: bold;">' + Object.keys(state.domainCount).length.toLocaleString() + '</td></tr>' +
    '<tr><td style="padding: 6px 10px;">Detected newsletters</td><td style="text-align: right; font-weight: bold; color: #e37400;">' + Object.keys(state.newsletterSenders).length + ' senders (' + Object.values(state.newsletterSenders).reduce(function(a, b) { return a + b; }, 0) + ' threads)</td></tr>' +
    (state.oldestDate ? '<tr><td style="padding: 6px 10px;">Oldest email</td><td style="text-align: right; font-weight: bold;">' + Utilities.formatDate(new Date(state.oldestDate), Session.getScriptTimeZone(), "MMM d, yyyy") + '</td></tr>' : '') +
    '<tr><td style="padding: 6px 10px;">Existing labels</td><td style="text-align: right; font-weight: bold;">' + existingLabels.length + '</td></tr>' +
    '</table></div>';

  // AGE DISTRIBUTION
  html += '<div style="background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0;">' +
    '<h2 style="margin-top: 0;">Age Distribution</h2>' +
    '<table style="width: 100%; border-collapse: collapse;">' +
    '<tr style="background: #e8eaed;"><th style="padding: 6px 10px; text-align: left;">Age</th><th style="text-align: right; padding: 6px 10px;">Threads</th><th style="text-align: right; padding: 6px 10px;">Unread</th><th style="text-align: right; padding: 6px 10px;">% of Inbox</th></tr>';
  Object.entries(state.ageBuckets).forEach(function(entry) {
    var bucket = entry[0], count = entry[1];
    var pct = totalThreads > 0 ? (count / totalThreads * 100).toFixed(1) : "0";
    var unread = state.unreadByAge[bucket] || 0;
    var barWidth = totalThreads > 0 ? Math.max(1, Math.round(count / totalThreads * 200)) : 0;
    html += '<tr><td style="padding: 6px 10px;">' + bucket + '</td>' +
      '<td style="text-align: right; padding: 6px 10px; font-weight: bold;">' + count.toLocaleString() + '</td>' +
      '<td style="text-align: right; padding: 6px 10px; color: #d93025;">' + (unread > 0 ? unread : "-") + '</td>' +
      '<td style="text-align: right; padding: 6px 10px;"><div style="display: inline-block; width: ' + barWidth + 'px; height: 12px; background: #1a73e8; border-radius: 2px; margin-right: 6px; vertical-align: middle;"></div>' + pct + '%</td></tr>';
  });
  html += '</table></div>';

  // TOP SENDERS
  html += '<div style="background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0;">' +
    '<h2 style="margin-top: 0;">Top 25 Senders</h2>' +
    '<table style="width: 100%; border-collapse: collapse;">' +
    '<tr style="background: #e8eaed;"><th style="padding: 6px 10px; text-align: left;">#</th><th style="text-align: left; padding: 6px 10px;">Sender</th><th style="text-align: right; padding: 6px 10px;">Threads</th></tr>';
  topSenders.forEach(function(entry, i) {
    html += '<tr><td style="padding: 4px 10px; color: #5f6368;">' + (i + 1) + '</td><td style="padding: 4px 10px;">' + escapeHtml_(entry[0]) + '</td><td style="text-align: right; padding: 4px 10px; font-weight: bold;">' + entry[1] + '</td></tr>';
  });
  html += '</table></div>';

  // TOP DOMAINS
  html += '<div style="background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0;">' +
    '<h2 style="margin-top: 0;">Top 25 Domains</h2>' +
    '<table style="width: 100%; border-collapse: collapse;">' +
    '<tr style="background: #e8eaed;"><th style="padding: 6px 10px; text-align: left;">#</th><th style="text-align: left; padding: 6px 10px;">Domain</th><th style="text-align: right; padding: 6px 10px;">Threads</th></tr>';
  topDomains.forEach(function(entry, i) {
    html += '<tr><td style="padding: 4px 10px; color: #5f6368;">' + (i + 1) + '</td><td style="padding: 4px 10px;">' + escapeHtml_(entry[0]) + '</td><td style="text-align: right; padding: 4px 10px; font-weight: bold;">' + entry[1] + '</td></tr>';
  });
  html += '</table></div>';

  // NEWSLETTERS
  if (topNewsletters.length > 0) {
    html += '<div style="background: #fef7e0; padding: 20px; border-radius: 8px; margin: 20px 0;">' +
      '<h2 style="margin-top: 0; color: #e37400;">Detected Newsletters (' + topNewsletters.length + ' senders)</h2>' +
      '<p style="color: #5f6368; margin-top: 0;">These senders have "unsubscribe" or similar patterns. Good candidates for auto-archive.</p>' +
      '<table style="width: 100%; border-collapse: collapse;">' +
      '<tr style="background: #fce8b2;"><th style="padding: 6px 10px; text-align: left;">Sender</th><th style="text-align: right; padding: 6px 10px;">Threads</th></tr>';
    topNewsletters.forEach(function(entry) {
      html += '<tr><td style="padding: 4px 10px;">' + escapeHtml_(entry[0]) + '</td><td style="text-align: right; padding: 4px 10px; font-weight: bold;">' + entry[1] + '</td></tr>';
    });
    html += '</table></div>';
  }

  // DAY OF WEEK
  html += '<div style="background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0;">' +
    '<h2 style="margin-top: 0;">Email Frequency by Day of Week</h2>' +
    '<table style="width: 100%; border-collapse: collapse;">';
  var maxDay = Math.max.apply(null, state.dayOfWeekCount);
  state.dayOfWeekCount.forEach(function(count, i) {
    var barWidth = maxDay > 0 ? Math.max(1, Math.round(count / maxDay * 200)) : 0;
    html += '<tr><td style="padding: 4px 10px; width: 100px;">' + dayNames[i] + '</td><td style="padding: 4px 10px;"><div style="display: inline-block; width: ' + barWidth + 'px; height: 14px; background: #34a853; border-radius: 2px; vertical-align: middle;"></div> ' + count + '</td></tr>';
  });
  html += '</table></div>';

  // PEAK HOURS
  html += '<div style="background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0;">' +
    '<h2 style="margin-top: 0;">Email Frequency by Hour</h2>' +
    '<table style="width: 100%; border-collapse: collapse;">';
  var maxHour = Math.max.apply(null, state.hourCount);
  state.hourCount.forEach(function(count, h) {
    if (count === 0) return;
    var barWidth = maxHour > 0 ? Math.max(1, Math.round(count / maxHour * 200)) : 0;
    var label = h === 0 ? "12 AM" : h < 12 ? h + " AM" : h === 12 ? "12 PM" : (h - 12) + " PM";
    html += '<tr><td style="padding: 2px 10px; width: 60px; font-size: 13px;">' + label + '</td><td style="padding: 2px 10px;"><div style="display: inline-block; width: ' + barWidth + 'px; height: 12px; background: #4285f4; border-radius: 2px; vertical-align: middle;"></div> ' + count + '</td></tr>';
  });
  html += '</table></div>';

  // LARGE EMAILS
  if (state.largeEmails.length > 0) {
    html += '<div style="background: #fce8e6; padding: 20px; border-radius: 8px; margin: 20px 0;">' +
      '<h2 style="margin-top: 0; color: #d93025;">Large Emails (top 15)</h2>' +
      '<p style="color: #5f6368; margin-top: 0;">These threads have large content. Consider archiving or deleting to free space.</p>' +
      '<table style="width: 100%; border-collapse: collapse; font-size: 13px;">' +
      '<tr style="background: #f4c7c3;"><th style="padding: 6px 8px; text-align: left;">Subject</th><th style="text-align: left; padding: 6px 8px;">From</th><th style="text-align: right; padding: 6px 8px;">Size</th><th style="text-align: right; padding: 6px 8px;">Date</th></tr>';
    state.largeEmails.forEach(function(e) {
      html += '<tr><td style="padding: 3px 8px;">' + escapeHtml_(e.subject) + '</td><td style="padding: 3px 8px;">' + escapeHtml_(e.from) + '</td><td style="text-align: right; padding: 3px 8px; font-weight: bold;">' + e.sizeKB + ' KB</td><td style="text-align: right; padding: 3px 8px;">' + e.date + '</td></tr>';
    });
    html += '</table></div>';
  }

  // EXISTING LABELS
  if (existingLabels.length > 0) {
    html += '<div style="background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0;">' +
      '<h2 style="margin-top: 0;">Existing Labels (' + existingLabels.length + ')</h2>' +
      '<table style="width: 100%; border-collapse: collapse;">' +
      '<tr style="background: #e8eaed;"><th style="padding: 6px 10px; text-align: left;">Label</th><th style="text-align: right; padding: 6px 10px;">Threads</th></tr>';
    existingLabels.slice(0, 30).forEach(function(l) {
      html += '<tr><td style="padding: 3px 10px;">' + escapeHtml_(l.name) + '</td><td style="text-align: right; padding: 3px 10px;">' + l.threads + '</td></tr>';
    });
    html += '</table></div>';
  }

  // SUGGESTIONS
  html += '<div style="background: #e6f4ea; padding: 20px; border-radius: 8px; margin: 20px 0;">' +
    '<h2 style="margin-top: 0; color: #137333;">Suggested Actions</h2><ol style="padding-left: 20px;">';
  suggestions.forEach(function(s) { html += '<li style="padding: 4px 0;">' + s + '</li>'; });
  html += '</ol></div>';

  html += '<p style="color: #5f6368; font-size: 12px; margin-top: 24px; border-top: 1px solid #dadce0; padding-top: 12px;">' +
    'This assessment is read-only &mdash; no emails were moved, labeled, or deleted.<br>' +
    'Next step: customize the CONFIG rules, then run <code>setup()</code> and <code>organizeAll()</code>.</p></div>';

  // Send
  var subject = "Gmail Assessment: " + totalThreads.toLocaleString() + " threads, " + state.unreadCount.toLocaleString() + " unread, " + Object.keys(state.newsletterSenders).length + " newsletters detected";
  GmailApp.sendEmail("me", subject,
    "Gmail Assessment: " + totalThreads + " threads, " + state.totalMessages + " messages. Open HTML version for full report.",
    { htmlBody: html });
}


function generateSuggestions_(topDomains, topSenders, topNewsletters, ageBuckets, totalThreads) {
  const suggestions = [];

  // Newsletter suggestion
  if (topNewsletters.length > 5) {
    suggestions.push(`<strong>Auto-archive ${topNewsletters.length} newsletter senders</strong> — these clutter your inbox. The script will label them "Newsletters" and archive automatically.`);
  }

  // Old email suggestion
  const oldCount = (ageBuckets["3-6 months"] || 0) + (ageBuckets["6-12 months"] || 0) + (ageBuckets["1-2 years"] || 0) + (ageBuckets["2+ years"] || 0);
  if (oldCount > 50) {
    suggestions.push(`<strong>Archive ${oldCount.toLocaleString()} old emails</strong> (3+ months) — they're still searchable after archiving, just won't clutter your inbox.`);
  }

  // High-volume senders
  const highVolume = topSenders.filter(([_, count]) => count > 20);
  if (highVolume.length > 0) {
    const names = highVolume.slice(0, 3).map(([s]) => `"${s}"`).join(", ");
    suggestions.push(`<strong>Create auto-label rules</strong> for high-volume senders like ${names} — keeps your inbox scannable.`);
  }

  // Domain consolidation
  const topDomainNames = topDomains.slice(0, 5).map(([d]) => d);
  if (topDomainNames.length > 0) {
    suggestions.push(`<strong>Your top domains</strong>: ${topDomainNames.join(", ")} — consider adding domain-based label rules for these in CONFIG.labelRules.`);
  }

  // General tips
  if (totalThreads > 500) {
    suggestions.push(`<strong>Enable daily digest</strong> — with ${totalThreads.toLocaleString()} inbox threads, a daily summary helps you stay on top of what matters.`);
  }

  suggestions.push(`<strong>Run a dry run first</strong> — use <code>dryRunAll()</code> to preview what the organizer would do before making real changes.`);

  return suggestions;
}

function escapeHtml_(str) {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}


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
