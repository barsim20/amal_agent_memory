"use client";

import React from "react";
import { CategoricalState, CategoryCardData } from "../types";

interface ClientWorkspaceProps {
  initialState: CategoricalState;
}

const SAMPLE_PROMPTS = [
  "I built a Socratic tutor skill using the skill-creator system and I do prompt optimization for WhatsApp agents.",
  "I teach Grade 6 Mathematics and Science with 65 learners, and we have no projector.",
  "I co-plan my Science lessons with my colleague Wanjiru.",
  "Help me create a 20-minute Hisabati lesson plan for my class",
  "What do you remember about me?",
];

const DEFAULT_IMPORT_PROMPT =
  "Export all of your stored memories, preferences, teaching context, and ongoing topics about me as a bulleted list of concise third-person statements (one fact per line) so I can import them into Amal.";

const INLINE_RUNTIME_SCRIPT = `
(function() {
  if (window.__AMAL_RUNTIME_BOUND__) return;
  window.__AMAL_RUNTIME_BOUND__ = true;

  var state = window.__AMAL_INITIAL_STATE__ || null;
  var viewMode = "split";
  var memoryDisplayMode = "list"; // "list" | "cards"
  var filterTab = "populated";
  var searchQuery = "";
  var showKeyBar = true;
  var creatingArea = false;
  var creatingSubcat = false;
  var showImportPanel = false;
  var activeCategorySlug = null;     // Layer 2 slug
  var activeSubcategorySlug = null;  // Layer 3 slug
  var chatHistory = [];
  var toastTimer = null;
  var messages = [
    {
      id: "welcome-1",
      role: "assistant",
      content: "Habari Mwalimu! I am Amal, your teaching assistant. Ask me anything or share something about your classroom and work."
    }
  ];

  function esc(str) {
    if (str === null || str === undefined) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function getTeacherId() {
    var el = document.getElementById("teacher-id-input");
    return (el && el.value.trim()) || (state && state.teacher && state.teacher.teacher_id) || "teacher-wambui-ke";
  }

  function getAnthropicApiKey() {
    var el = document.getElementById("session-anthropic-key-input");
    if (el && el.value.trim()) return el.value.trim();
    try { return window.localStorage.getItem("amal_anthropic_api_key") || ""; } catch (e) { return ""; }
  }

  function getGeminiApiKey() {
    var el = document.getElementById("session-gemini-key-input");
    if (el && el.value.trim()) return el.value.trim();
    try { return window.localStorage.getItem("amal_gemini_api_key") || ""; } catch (e) { return ""; }
  }

  function initSavedKeys() {
    try {
      var savedAnt = window.localStorage.getItem("amal_anthropic_api_key") || "";
      var savedGem = window.localStorage.getItem("amal_gemini_api_key") || "";
      var antEl = document.getElementById("session-anthropic-key-input");
      var gemEl = document.getElementById("session-gemini-key-input");
      if (antEl && savedAnt && !antEl.value) antEl.value = savedAnt;
      if (gemEl && savedGem && !gemEl.value) gemEl.value = savedGem;
    } catch (e) {}
  }

  function showMemoryToast(messageText) {
    var container = document.getElementById("amal-toast-container");
    if (!container) return;
    container.innerHTML =
      '<div class="amal-toast" role="status" aria-live="polite">' +
        '<div>' +
          '<div style="font-weight:600;">' + esc(messageText || "Amal learned something new about you.") + '</div>' +
          '<div style="font-size:12px; color:rgba(255,255,255,0.82); margin-top:2px;">Discover in memories</div>' +
        '</div>' +
        '<div class="amal-toast-actions">' +
          '<button type="button" class="amal-toast-link" data-action="toast-discover-memories">Discover in memories</button>' +
          '<button type="button" class="amal-toast-dismiss" data-action="toast-dismiss">Dismiss</button>' +
        '</div>' +
      '</div>';
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(function() {
      if (container) container.innerHTML = "";
    }, 9000);
  }

  function updateViewModeUI() {
    var btns = document.querySelectorAll("[data-view-mode]");
    for (var i = 0; i < btns.length; i++) {
      var m = btns[i].getAttribute("data-view-mode");
      if (m === viewMode) btns[i].classList.add("active");
      else btns[i].classList.remove("active");
    }
    var layout = document.getElementById("workspace-layout");
    var chatCol = document.getElementById("chat-column-wrap");
    var dashCol = document.getElementById("dashboard-column-wrap");
    if (!layout || !chatCol || !dashCol) return;

    if (viewMode === "split") {
      layout.className = "workspace-split";
      layout.style.maxWidth = "";
      chatCol.style.display = "block";
      dashCol.style.display = "block";
    } else if (viewMode === "chat") {
      layout.className = "workspace-single";
      layout.style.maxWidth = "860px";
      chatCol.style.display = "block";
      dashCol.style.display = "none";
    } else {
      layout.className = "workspace-single";
      layout.style.maxWidth = "1180px";
      chatCol.style.display = "none";
      dashCol.style.display = "block";
    }
  }

  function updateDisplayModeButtons() {
    var btns = document.querySelectorAll("[data-display-mode]");
    for (var i = 0; i < btns.length; i++) {
      var dm = btns[i].getAttribute("data-display-mode");
      if (dm === memoryDisplayMode) btns[i].classList.add("active");
      else btns[i].classList.remove("active");
    }
  }

  function renderChatStream() {
    var stream = document.getElementById("chat-stream-container");
    if (!stream) return;
    var html = "";
    for (var i = 0; i < messages.length; i++) {
      var msg = messages[i];
      html += '<div class="chat-bubble-wrap ' + esc(msg.role) + '">';
      html += '<div class="chat-bubble ' + esc(msg.role) + '">' + esc(msg.content) + '</div>';
      html += '</div>';
    }
    stream.innerHTML = html;
    stream.scrollTop = stream.scrollHeight;
  }

  function getAllCategories() {
    if (!state) return [];
    var list = [];
    var core = state.core_categories || [];
    var las = state.life_areas || [];
    for (var i = 0; i < core.length; i++) list.push(core[i]);
    for (var j = 0; j < las.length; j++) list.push(las[j]);
    return list;
  }

  function findCategoryBySlug(slug) {
    if (!slug || !state) return null;
    var all = getAllCategories();
    for (var i = 0; i < all.length; i++) {
      if (all[i].slug === slug) return all[i];
    }
    return null;
  }

  function findSubcategoryBySlug(cat, subSlug) {
    if (!cat || !subSlug) return null;
    var subs = cat.subcategories || [];
    for (var i = 0; i < subs.length; i++) {
      if (subs[i].slug === subSlug) return subs[i];
    }
    return null;
  }

  function getYouAndTopicsGroups(matchesFn) {
    var youItems = [];
    var topicItems = [];
    var youSlugs = {
      preferences: true,
      profile: true,
      teaching_context: true,
      classroom: true,
      people: true,
      wellbeing: true,
      named_learners: true
    };
    var all = getAllCategories();
    for (var i = 0; i < all.length; i++) {
      var cat = all[i];
      var isLa = Boolean(cat.is_life_area);
      if (filterTab === "life_areas" && !isLa) continue;
      if (filterTab === "populated" && (cat.memories || []).length === 0 && !isLa) continue;
      if (matchesFn && !matchesFn(cat)) continue;

      var sec = cat.section || (youSlugs[cat.slug] && !isLa ? "you" : "topics");
      if (sec === "you") youItems.push(cat);
      else topicItems.push(cat);
    }
    return { you: youItems, topics: topicItems };
  }

  function renderCategoryCardHtml(cat, isLifeArea) {
    var html = '<article class="memory-card" id="category-card-' + esc(cat.slug) + '">';
    html += '<div class="memory-card-header">';
    html += '<div class="memory-card-title-group">';
    html += '<h3 class="memory-card-title" style="cursor:pointer;" data-action="open-category" data-slug="' + esc(cat.slug) + '">' + esc(cat.label_en) + '</h3>';
    if (isLifeArea) html += '<span class="tag life-area">Life Area</span>';
    if (cat.status === "archived") html += '<span class="tag">Archived</span>';
    if (cat.sensitivity === "consent") html += '<span class="tag consent">Consent required</span>';
    html += '</div>';
    html += '<div style="display:flex; gap:6px; align-items:center;">';
    html += '<button type="button" class="btn btn-xs" data-action="open-category" data-slug="' + esc(cat.slug) + '">Open &rarr;</button>';
    if (isLifeArea) {
      html += '<button type="button" class="btn btn-xs" data-action="rename-life-area" data-id="' + esc(cat.id) + '" data-label="' + esc(cat.label_en) + '">Rename</button>';
      if (cat.status === "archived") {
        html += '<button type="button" class="btn btn-xs" data-action="restore-life-area" data-id="' + esc(cat.id) + '">Restore</button>';
      }
    }
    html += '<button type="button" class="btn btn-danger-ghost" data-action="delete-category" data-id="' + esc(cat.id) + '" data-life-area="' + (isLifeArea ? "1" : "0") + '">Delete</button>';
    html += '</div></div>';

    html += '<div class="memory-field-block"><div class="memory-field-label">Last updated</div><div class="memory-field-value">' + esc(cat.last_updated || "No memories saved yet") + '</div></div>';
    html += '<div class="memory-field-block"><div class="memory-field-label">Summary</div><div class="memory-field-value">' + esc(cat.summary || cat.description || "") + '</div></div>';

    var subs = cat.subcategories || [];
    if (subs.length > 0) {
      html += '<div class="memory-field-block"><div class="memory-field-label">Layer 3 Subcategories (click to inspect)</div>';
      html += '<div class="subcat-pills-row" style="margin-top:6px;">';
      for (var sIdx = 0; sIdx < subs.length; sIdx++) {
        var sc = subs[sIdx];
        var cnt = sc.memory_count || (sc.memories ? sc.memories.length : 0);
        html += '<button type="button" class="subcat-layer-pill" data-action="open-subcategory" data-cat-slug="' + esc(cat.slug) + '" data-sub-slug="' + esc(sc.slug) + '">';
        html += '<span>' + esc(sc.label_en) + '</span>';
        html += '<span class="subcat-count">' + cnt + '</span>';
        html += '</button>';
      }
      html += '</div></div>';
    }

    html += '<div class="memory-field-block" style="margin-bottom:0;"><div class="memory-field-label">Details</div>';
    var mems = cat.memories || [];
    if (mems.length > 0) {
      html += '<ul class="memory-details-list">';
      for (var i = 0; i < mems.length; i++) {
        var m = mems[i];
        html += '<li class="memory-details-item"><div class="memory-bullet-row">';
        html += '<div><span>' + esc(m.statement) + '</span>';
        if (m.subcategory_label) {
          html += ' <button type="button" class="subcat-layer-pill" style="padding:1px 7px; font-size:11px; margin-left:6px;" data-action="open-subcategory" data-cat-slug="' + esc(cat.slug) + '" data-sub-slug="' + esc(m.subcategory_slug || "general") + '">' + esc(m.subcategory_label) + ' &rarr;</button>';
        }
        html += '</div>';
        html += '<div class="memory-bullet-actions" style="opacity:1;">';
        html += '<button type="button" class="btn btn-xs" data-action="edit-memory" data-id="' + esc(m.id) + '" data-statement="' + esc(m.statement) + '">Edit</button>';
        html += '<button type="button" class="btn btn-xs btn-danger-ghost" data-action="delete-memory" data-id="' + esc(m.id) + '">Delete</button>';
        html += '</div></div></li>';
      }
      html += '</ul>';
    } else {
      html += '<div style="font-size:13px; color:var(--text-muted); margin-top:4px;">No details saved in this category yet.</div>';
    }
    html += '</div>';

    html += '<div class="memory-card-footer">';
    html += '<span style="font-size:11.5px; color:var(--text-muted);">' + esc(cat.label_sw) + '</span>';
    html += '<div style="display:flex; gap:6px;">';
    html += '<button type="button" class="btn btn-xs" data-action="add-detail" data-slug="' + esc(cat.slug) + '" data-label="' + esc(cat.label_en) + '">Add detail</button>';
    html += '</div></div></article>';
    return html;
  }

  function renderImportBannerAndModal() {
    var html = '<div class="claude-import-banner">';
    html += '<div class="claude-import-banner-text">';
    html += '<div class="claude-import-banner-title">Import memory from other AI providers</div>';
    html += '<div class="claude-import-banner-sub">Bring relevant context and data from another AI provider to Amal. We&#39;ll provide a prompt you can use to fetch the memory from your other account.</div>';
    html += '</div>';
    html += '<button type="button" class="btn" data-action="toggle-import-memory">' + (showImportPanel ? "Close import" : "Start import") + '</button>';
    html += '</div>';

    if (showImportPanel) {
      html += '<div class="minimal-panel" style="margin-bottom:24px; display:flex; flex-direction:column; gap:12px;">';
      html += '<div style="display:flex; justify-content:space-between; align-items:center;">';
      html += '<strong style="font-size:14px;">Step 1: Copy this prompt to your other AI assistant (Claude, ChatGPT, Gemini)</strong>';
      html += '<button type="button" class="btn btn-xs" data-action="copy-import-prompt">Copy prompt</button>';
      html += '</div>';
      html += '<pre class="mono-block" id="import-prompt-pre" style="margin:0;">' + esc('Export all of your stored memories, preferences, teaching context, and ongoing topics about me as a bulleted list of concise third-person statements (one fact per line) so I can import them into Amal.') + '</pre>';
      html += '<strong style="font-size:14px;">Step 2: Paste the exported memories below (one bullet per line)</strong>';
      html += '<textarea id="import-memories-textarea" class="input" rows="5" style="width:100%; font-family:var(--font-sans); resize:vertical;" placeholder="- Never use em dashes in any response or generated content&#10;- Prefers studying academic/course content in English&#10;- Built a Socratic tutor skill using the skill-creator system"></textarea>';
      html += '<div style="display:flex; justify-content:flex-end; gap:8px;">';
      html += '<button type="button" class="btn" data-action="toggle-import-memory">Cancel</button>';
      html += '<button type="button" class="btn btn-primary" data-action="submit-import-memories">Import into Amal</button>';
      html += '</div></div>';
    }
    return html;
  }

  function renderBottomMemoryInputBar(placeholderText, targetCatSlug, targetSubSlug) {
    var ph = placeholderText || "My dog's name is Beans";
    var html = '<div class="claude-bottom-input-wrap">';
    html += '<div class="claude-bottom-input-bar">';
    html += '<input type="text" id="claude-memory-quick-input" class="claude-bottom-input" placeholder="' + esc(ph) + '" data-cat-slug="' + esc(targetCatSlug || "") + '" data-sub-slug="' + esc(targetSubSlug || "") + '" />';
    html += '<button type="button" class="claude-up-btn" data-action="submit-quick-memory" data-cat-slug="' + esc(targetCatSlug || "") + '" data-sub-slug="' + esc(targetSubSlug || "") + '" title="Save to memory" aria-label="Save to memory">&uarr;</button>';
    html += '</div></div>';
    return html;
  }

  function renderLayer1Overview(matchesFn) {
    var groups = getYouAndTopicsGroups(matchesFn);
    var youList = groups.you;
    var topicList = groups.topics;
    var html = '<div class="claude-memory-shell">';

    // Top breadcrumb bar matching image.png
    html += '<div class="claude-breadcrumb-bar">';
    html += '<span style="color:var(--text-secondary);">&larr; Your Amal</span>';
    html += '<span class="sep">/</span>';
    html += '<span class="current">Memory</span>';
    html += '<span class="tag" style="margin-left:auto;">Layer 1 of 3 &middot; You &amp; Topics</span>';
    html += '</div>';

    html += renderImportBannerAndModal();

    if (memoryDisplayMode === "list") {
      // Claude-style List View (image.png)
      html += '<div class="claude-section-block">';
      html += '<h3 class="claude-section-heading">You</h3>';
      if (youList.length > 0) {
        html += '<div class="claude-list-table" role="list">';
        for (var i = 0; i < youList.length; i++) {
          var yc = youList[i];
          var yDate = yc.last_updated_short || (yc.memories && yc.memories.length > 0 ? ("Updated " + yc.last_updated) : "Empty");
          html += '<div class="claude-list-row" role="listitem" tabindex="0" data-action="open-category" data-slug="' + esc(yc.slug) + '">';
          html += '<div class="claude-list-title">' + esc(yc.label_en) + '</div>';
          html += '<div class="claude-list-summary">' + esc(yc.summary || yc.description || "") + '</div>';
          html += '<div class="claude-list-date">' + esc(yDate) + '</div>';
          html += '</div>';
        }
        html += '</div>';
      } else {
        html += '<div style="font-size:13.5px; color:var(--text-muted); padding:8px 0;">No populated categories under You match the current filter.</div>';
      }
      html += '</div>';

      html += '<div class="claude-section-block">';
      html += '<h3 class="claude-section-heading">Topics</h3>';
      if (topicList.length > 0) {
        html += '<div class="claude-list-table" role="list">';
        for (var j = 0; j < topicList.length; j++) {
          var tc = topicList[j];
          var tDate = tc.last_updated_short || (tc.memories && tc.memories.length > 0 ? ("Updated " + tc.last_updated) : "Empty");
          html += '<div class="claude-list-row" role="listitem" tabindex="0" data-action="open-category" data-slug="' + esc(tc.slug) + '">';
          html += '<div class="claude-list-title">' + esc(tc.label_en) + '</div>';
          html += '<div class="claude-list-summary">' + esc(tc.summary || tc.description || "") + '</div>';
          html += '<div class="claude-list-date">' + esc(tDate) + '</div>';
          html += '</div>';
        }
        html += '</div>';
      } else {
        html += '<div style="font-size:13.5px; color:var(--text-muted); padding:8px 0;">No populated topics match the current filter.</div>';
      }
      html += '</div>';
    } else {
      // Cards View grouped by You and Topics
      html += '<div class="claude-section-block">';
      html += '<h3 class="claude-section-heading">You</h3>';
      if (youList.length > 0) {
        html += '<div class="cards-grid">';
        for (var k = 0; k < youList.length; k++) {
          html += renderCategoryCardHtml(youList[k], Boolean(youList[k].is_life_area));
        }
        html += '</div>';
      } else {
        html += '<div style="font-size:13.5px; color:var(--text-muted); padding:8px 0;">No populated cards under You.</div>';
      }
      html += '</div>';

      html += '<div class="claude-section-block">';
      html += '<h3 class="claude-section-heading">Topics</h3>';
      if (topicList.length > 0) {
        html += '<div class="cards-grid">';
        for (var m = 0; m < topicList.length; m++) {
          html += renderCategoryCardHtml(topicList[m], Boolean(topicList[m].is_life_area));
        }
        html += '</div>';
      } else {
        html += '<div style="font-size:13.5px; color:var(--text-muted); padding:8px 0;">No populated cards under Topics.</div>';
      }
      html += '</div>';
    }

    if (youList.length === 0 && topicList.length === 0) {
      html += '<div class="minimal-panel"><div style="font-size:14px; color:var(--text-secondary);">No categories with active memories match the current filter. Click <button type="button" class="btn btn-xs" data-filter-tab="all">All Categories</button> or click <strong>Seed Demo</strong> in the top bar.</div></div>';
    }

    html += renderBottomMemoryInputBar("My dog's name is Beans", "", "");
    html += '</div>';
    return html;
  }

  function renderLayer2CategoryDetail(cat) {
    var isLifeArea = Boolean(cat.is_life_area);
    var subs = cat.subcategories || [];
    var mems = cat.memories || [];

    var html = '<div class="claude-memory-shell"><div class="claude-detail-view">';

    // Back navigation matching image_2.png ("<- Memory")
    html += '<div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:20px;">';
    html += '<button type="button" class="claude-back-link" style="margin-bottom:0;" data-action="back-to-layer-1">&larr; Memory</button>';
    html += '<span class="tag">Layer 2 of 3 &middot; ' + (cat.section === "you" ? "You" : "Topics") + ' / ' + esc(cat.label_en) + '</span>';
    html += '</div>';

    // Header row: Category title on left, Delete & Rename on right (image_2.png)
    html += '<div class="claude-detail-header" id="layer2-detail-header">';
    html += '<div style="display:flex; align-items:center; gap:10px; flex-wrap:wrap;">';
    html += '<h2 class="claude-detail-title">' + esc(cat.label_en) + '</h2>';
    if (isLifeArea) html += '<span class="tag life-area">Life Area</span>';
    if (cat.sensitivity === "consent") html += '<span class="tag consent">Consent required</span>';
    html += '</div>';
    html += '<div class="claude-detail-actions">';
    html += '<button type="button" class="btn btn-danger-ghost" data-action="delete-category" data-id="' + esc(cat.id) + '" data-life-area="' + (isLifeArea ? "1" : "0") + '">Delete</button>';
    if (isLifeArea) {
      html += '<button type="button" class="btn" data-action="rename-life-area" data-id="' + esc(cat.id) + '" data-label="' + esc(cat.label_en) + '">Rename</button>';
    } else {
      html += '<button type="button" class="btn" data-action="toggle-new-subcategory" data-cat-id="' + esc(cat.id) + '">+ Subcategory</button>';
    }
    html += '</div></div>';

    // Last updated
    html += '<div class="claude-detail-section">';
    html += '<div class="claude-detail-label">Last updated</div>';
    html += '<div class="claude-detail-text">' + esc(cat.last_updated || "No memories saved yet") + '</div>';
    html += '</div>';

    // Summary
    html += '<div class="claude-detail-section">';
    html += '<div class="claude-detail-label">Summary</div>';
    html += '<div class="claude-detail-text">' + esc(cat.summary || cat.description || "") + '</div>';
    html += '</div>';

    // Layer 3 Subcategories section (clickable to drill into Layer 3)
    html += '<div class="claude-detail-section">';
    html += '<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">';
    html += '<div class="claude-detail-label" style="margin-bottom:0;">Subcategories (Click to open Layer 3)</div>';
    html += '<button type="button" class="btn btn-xs" data-action="toggle-new-subcategory" data-cat-id="' + esc(cat.id) + '">' + (creatingSubcat ? "Cancel" : "+ New Subcategory") + '</button>';
    html += '</div>';

    if (creatingSubcat) {
      html += '<div class="minimal-panel" style="margin-bottom:12px; display:flex; gap:8px; align-items:center; flex-wrap:wrap;">';
      html += '<input type="text" id="new-subcat-en-input" class="input" placeholder="Subcategory name (e.g. Prompting workflows)" style="flex:1; min-width:180px;" />';
      html += '<input type="text" id="new-subcat-sw-input" class="input" placeholder="Swahili label (optional)" style="width:180px;" />';
      html += '<button type="button" class="btn btn-xs btn-primary" data-action="create-subcategory-submit" data-parent-id="' + esc(cat.id) + '">Add Subcategory</button>';
      html += '</div>';
    }

    if (subs.length > 0) {
      if (memoryDisplayMode === "list") {
        html += '<div class="claude-list-table" role="list" style="margin-top:4px;">';
        for (var s = 0; s < subs.length; s++) {
          var sub = subs[s];
          var subCount = sub.memory_count || (sub.memories ? sub.memories.length : 0);
          html += '<div class="claude-list-row" role="listitem" tabindex="0" data-action="open-subcategory" data-cat-slug="' + esc(cat.slug) + '" data-sub-slug="' + esc(sub.slug) + '">';
          html += '<div class="claude-list-title">' + esc(sub.label_en) + ' <span class="tag" style="margin-left:4px;">' + subCount + '</span></div>';
          html += '<div class="claude-list-summary">' + esc(sub.summary || ("No details in " + sub.label_en + " yet.")) + '</div>';
          html += '<div class="claude-list-date">' + esc(sub.last_updated_short || "Open Layer 3 &rarr;") + '</div>';
          html += '</div>';
        }
        html += '</div>';
      } else {
        html += '<div class="cards-grid" style="margin-top:8px;">';
        for (var scIdx = 0; scIdx < subs.length; scIdx++) {
          var scObj = subs[scIdx];
          var scCount = scObj.memory_count || (scObj.memories ? scObj.memories.length : 0);
          html += '<article class="memory-card" style="cursor:pointer;" data-action="open-subcategory" data-cat-slug="' + esc(cat.slug) + '" data-sub-slug="' + esc(scObj.slug) + '">';
          html += '<div class="memory-card-header"><div class="memory-card-title-group"><h3 class="memory-card-title">' + esc(scObj.label_en) + '</h3><span class="tag">' + scCount + ' details</span></div>';
          html += '<span style="font-size:12px; color:var(--accent); font-weight:500;">Layer 3 &rarr;</span></div>';
          html += '<div class="memory-field-block" style="margin-bottom:0;"><div class="memory-field-value">' + esc(scObj.summary || "") + '</div></div>';
          html += '</article>';
        }
        html += '</div>';
      }
    }
    html += '</div>';

    // Details section matching image_2.png
    html += '<div class="claude-detail-section">';
    html += '<div class="claude-detail-label">Details</div>';
    if (mems.length > 0) {
      if (memoryDisplayMode === "list") {
        html += '<ul class="claude-detail-bullets">';
        for (var i = 0; i < mems.length; i++) {
          var m = mems[i];
          html += '<li><div class="memory-bullet-row">';
          html += '<div><span>' + esc(m.statement) + '</span>';
          if (m.subcategory_label) {
            html += ' <button type="button" class="subcat-layer-pill" style="padding:1px 8px; font-size:11px; margin-left:6px;" data-action="open-subcategory" data-cat-slug="' + esc(cat.slug) + '" data-sub-slug="' + esc(m.subcategory_slug || "general") + '">' + esc(m.subcategory_label) + '</button>';
          }
          html += '</div>';
          html += '<div class="memory-bullet-actions" style="opacity:1;">';
          html += '<button type="button" class="btn btn-xs" data-action="edit-memory" data-id="' + esc(m.id) + '" data-statement="' + esc(m.statement) + '">Edit</button>';
          html += '<button type="button" class="btn btn-xs btn-danger-ghost" data-action="delete-memory" data-id="' + esc(m.id) + '">Delete</button>';
          html += '</div></div></li>';
        }
        html += '</ul>';
      } else {
        html += '<div class="cards-grid" style="margin-top:8px;">';
        for (var mIdx = 0; mIdx < mems.length; mIdx++) {
          var memCard = mems[mIdx];
          html += '<article class="memory-card">';
          html += '<div class="memory-bullet-row" style="margin-bottom:8px;"><strong>' + esc(memCard.statement) + '</strong></div>';
          html += '<div style="display:flex; justify-content:space-between; align-items:center; font-size:12px; color:var(--text-muted);">';
          html += '<span>' + esc(memCard.subcategory_label || "General") + ' &middot; ' + esc(memCard.source) + '</span>';
          html += '<div style="display:flex; gap:6px;">';
          html += '<button type="button" class="btn btn-xs" data-action="edit-memory" data-id="' + esc(memCard.id) + '" data-statement="' + esc(memCard.statement) + '">Edit</button>';
          html += '<button type="button" class="btn btn-xs btn-danger-ghost" data-action="delete-memory" data-id="' + esc(memCard.id) + '">Delete</button>';
          html += '</div></div></article>';
        }
        html += '</div>';
      }
    } else {
      html += '<div style="font-size:14px; color:var(--text-muted);">No details saved in ' + esc(cat.label_en) + ' yet. Use the input bar below to add one.</div>';
    }
    html += '</div>';

    // Bottom pill input bar matching image_2.png ("My dog's name is Beans" + up arrow)
    html += renderBottomMemoryInputBar("My dog's name is Beans", cat.slug, "");
    html += '</div></div>';
    return html;
  }

  function renderLayer3SubcategoryDetail(cat, sub) {
    var mems = sub.memories || [];
    var siblingSubs = cat.subcategories || [];

    var html = '<div class="claude-memory-shell"><div class="claude-detail-view">';

    // Breadcrumb & Back navigation to Layer 2
    html += '<div style="display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:8px; margin-bottom:16px;">';
    html += '<div style="display:flex; align-items:center; gap:8px; font-size:13.5px;">';
    html += '<button type="button" class="claude-back-link" style="margin-bottom:0;" data-action="open-category" data-slug="' + esc(cat.slug) + '">&larr; ' + esc(cat.label_en) + '</button>';
    html += '<span style="color:var(--text-muted);">/</span>';
    html += '<button type="button" class="claude-back-link" style="margin-bottom:0;" data-action="back-to-layer-1">Memory</button>';
    html += '<span style="color:var(--text-muted);">/</span>';
    html += '<button type="button" class="claude-back-link" style="margin-bottom:0;" data-action="open-category" data-slug="' + esc(cat.slug) + '">' + esc(cat.label_en) + '</button>';
    html += '<span style="color:var(--text-muted);">/</span>';
    html += '<strong style="color:var(--text-primary);">' + esc(sub.label_en) + '</strong>';
    html += '</div>';
    html += '<span class="tag life-area">Layer 3 of 3 &middot; Subcategory</span>';
    html += '</div>';

    // Sibling subcategory switcher bar
    if (siblingSubs.length > 1) {
      html += '<div class="subcat-pills-row" style="margin-bottom:20px;">';
      for (var i = 0; i < siblingSubs.length; i++) {
        var sib = siblingSubs[i];
        var isCurrent = sib.slug === sub.slug;
        var cnt = sib.memory_count || (sib.memories ? sib.memories.length : 0);
        html += '<button type="button" class="subcat-layer-pill ' + (isCurrent ? 'active' : '') + '" data-action="open-subcategory" data-cat-slug="' + esc(cat.slug) + '" data-sub-slug="' + esc(sib.slug) + '">';
        html += '<span>' + esc(sib.label_en) + '</span>';
        html += '<span class="subcat-count">' + cnt + '</span>';
        html += '</button>';
      }
      html += '</div>';
    }

    // Header row: Subcategory title on left, Delete & Rename on right
    html += '<div class="claude-detail-header" id="layer3-detail-header">';
    html += '<div>';
    html += '<h2 class="claude-detail-title">' + esc(sub.label_en) + '</h2>';
    if (sub.label_sw) {
      html += '<div style="font-size:12.5px; color:var(--text-muted); margin-top:2px;">' + esc(sub.label_sw) + ' &middot; Subcategory of ' + esc(cat.label_en) + '</div>';
    }
    html += '</div>';
    html += '<div class="claude-detail-actions">';
    if (sub.id && String(sub.id).indexOf("virtual-") !== 0) {
      html += '<button type="button" class="btn btn-danger-ghost" data-action="delete-subcategory" data-id="' + esc(sub.id) + '" data-cat-slug="' + esc(cat.slug) + '">Delete</button>';
      html += '<button type="button" class="btn" data-action="rename-subcategory" data-id="' + esc(sub.id) + '" data-label="' + esc(sub.label_en) + '">Rename</button>';
    }
    html += '</div></div>';

    // Last updated
    html += '<div class="claude-detail-section">';
    html += '<div class="claude-detail-label">Last updated</div>';
    html += '<div class="claude-detail-text">' + esc(sub.last_updated || "No memories saved yet") + '</div>';
    html += '</div>';

    // Summary
    html += '<div class="claude-detail-section">';
    html += '<div class="claude-detail-label">Summary</div>';
    html += '<div class="claude-detail-text">' + esc(sub.summary || "") + '</div>';
    html += '</div>';

    // Details in Layer 3
    html += '<div class="claude-detail-section">';
    html += '<div class="claude-detail-label">Details (' + mems.length + ')</div>';
    if (mems.length > 0) {
      if (memoryDisplayMode === "list") {
        html += '<ul class="claude-detail-bullets">';
        for (var j = 0; j < mems.length; j++) {
          var m = mems[j];
          html += '<li><div class="memory-bullet-row">';
          html += '<div><div>' + esc(m.statement) + '</div>';
          html += '<div style="font-size:11.5px; color:var(--text-muted); margin-top:2px;">Source: ' + esc(m.source) + ' &middot; Surface: ' + esc(m.surface) + ' &middot; Confidence: ' + Math.round((m.confidence || 1) * 100) + '%</div></div>';
          html += '<div class="memory-bullet-actions" style="opacity:1;">';
          html += '<button type="button" class="btn btn-xs" data-action="edit-memory" data-id="' + esc(m.id) + '" data-statement="' + esc(m.statement) + '">Edit</button>';
          html += '<button type="button" class="btn btn-xs btn-danger-ghost" data-action="delete-memory" data-id="' + esc(m.id) + '">Delete</button>';
          html += '</div></div></li>';
        }
        html += '</ul>';
      } else {
        html += '<div class="cards-grid" style="margin-top:8px;">';
        for (var k = 0; k < mems.length; k++) {
          var mc = mems[k];
          html += '<article class="memory-card">';
          html += '<div class="memory-bullet-row" style="margin-bottom:8px;"><strong>' + esc(mc.statement) + '</strong></div>';
          html += '<div style="display:flex; justify-content:space-between; align-items:center; font-size:12px; color:var(--text-muted);">';
          html += '<span>Source: ' + esc(mc.source) + ' &middot; Confidence: ' + Math.round((mc.confidence || 1) * 100) + '%</span>';
          html += '<div style="display:flex; gap:6px;">';
          html += '<button type="button" class="btn btn-xs" data-action="edit-memory" data-id="' + esc(mc.id) + '" data-statement="' + esc(mc.statement) + '">Edit</button>';
          html += '<button type="button" class="btn btn-xs btn-danger-ghost" data-action="delete-memory" data-id="' + esc(mc.id) + '">Delete</button>';
          html += '</div></div></article>';
        }
        html += '</div>';
      }
    } else {
      html += '<div style="font-size:14px; color:var(--text-muted);">No details saved in ' + esc(sub.label_en) + ' yet. Use the input bar below to add a memory to this subcategory.</div>';
    }
    html += '</div>';

    // Bottom pill input bar scoped to this Layer 3 subcategory
    html += renderBottomMemoryInputBar("My dog's name is Beans", cat.slug, sub.slug);
    html += '</div></div>';
    return html;
  }

  function renderDashboard() {
    if (!state) return;
    updateDisplayModeButtons();

    var brandSub = document.getElementById("brand-subtitle-text");
    if (brandSub && state.teacher) {
      brandSub.textContent = state.teacher.display_name + " · " + state.teacher.curriculum;
    }

    var exportLink = document.getElementById("export-json-link");
    if (exportLink) {
      exportLink.setAttribute("href", "/api/memories/export?teacher_id=" + encodeURIComponent(getTeacherId()));
    }

    // Alerts stack
    var alertsEl = document.getElementById("alerts-stack-container");
    if (alertsEl) {
      var alertsHtml = "";
      var notifs = state.notifications || [];
      var activeBanners = notifs.filter(function(n) {
        return (n.kind === "saved" || n.kind === "updated") && n.action === "pending" && !n.seen_at;
      });
      if (state.settings && state.settings.banner_mode === "realtime" && activeBanners.length > 0) {
        var b = activeBanners[0];
        alertsHtml += '<div class="notice-bar saved"><div><div style="font-weight:600; font-size:13.5px;">Amal learned something new about you. Discover in memories</div>';
        alertsHtml += '</div><div style="display:flex; gap:6px;">';
        alertsHtml += '<button type="button" class="btn btn-xs" data-action="notif-action" data-id="' + esc(b.id) + '" data-act="kept">Keep</button>';
        alertsHtml += '<button type="button" class="btn btn-xs btn-danger-ghost" data-action="notif-action" data-id="' + esc(b.id) + '" data-act="undo">Undo</button>';
        alertsHtml += '</div></div>';
      }

      var consents = state.pending_consents || [];
      for (var c = 0; c < consents.length; c++) {
        var ci = consents[c];
        alertsHtml += '<div class="notice-bar consent"><div>';
        alertsHtml += '<div style="display:flex; align-items:center; gap:8px;"><span class="tag consent">' + esc(ci.category_label) + '</span><strong style="font-size:13.5px;">Amal would like to remember this. Keep it?</strong></div>';
        alertsHtml += '<div style="margin-top:4px; font-size:13.5px;">&ldquo;' + esc(ci.statement) + '&rdquo;</div>';
        alertsHtml += '<div class="notice-meta">Excluded from retrieval until approved · ' + esc(ci.prompt_text) + '</div>';
        alertsHtml += '</div><div style="display:flex; gap:6px;">';
        alertsHtml += '<button type="button" class="btn btn-xs btn-primary" data-action="resolve-consent" data-id="' + esc(ci.consent_id) + '" data-ans="yes">Yes, Keep</button>';
        alertsHtml += '<button type="button" class="btn btn-xs btn-danger-ghost" data-action="resolve-consent" data-id="' + esc(ci.consent_id) + '" data-ans="no">No, Delete</button>';
        alertsHtml += '</div></div>';
      }

      var taxNotifs = notifs.filter(function(n) {
        return n.kind === "taxonomy_change" && n.action === "pending" && n.changeset_status === "applied";
      });
      for (var t = 0; t < taxNotifs.length; t++) {
        var tn = taxNotifs[t];
        alertsHtml += '<div class="notice-bar"><div>';
        alertsHtml += '<div style="display:flex; align-items:center; gap:8px;"><span class="tag life-area">Nightly Dreaming</span><strong style="font-size:13.5px;">' + esc(tn.title) + '</strong></div>';
        alertsHtml += '<div class="notice-meta">' + esc(tn.body) + '</div></div><div style="display:flex; gap:6px;">';
        alertsHtml += '<button type="button" class="btn btn-xs" data-action="notif-action" data-id="' + esc(tn.id) + '" data-act="kept">Keep</button>';
        if (tn.changeset_id) {
          alertsHtml += '<button type="button" class="btn btn-xs btn-danger-ghost" data-action="undo-changeset" data-id="' + esc(tn.changeset_id) + '">Undo</button>';
        }
        alertsHtml += '</div></div>';
      }
      alertsEl.innerHTML = alertsHtml;
      alertsEl.style.display = alertsHtml ? "flex" : "none";
    }

    // Filter tabs counts
    var lifeAreas = state.life_areas || [];
    var coreCats = state.core_categories || [];
    var totalMems = 0;
    for (var i = 0; i < lifeAreas.length; i++) totalMems += (lifeAreas[i].memories || []).length;
    for (var j = 0; j < coreCats.length; j++) totalMems += (coreCats[j].memories || []).length;

    var tabPop = document.getElementById("tab-btn-populated");
    var tabAll = document.getElementById("tab-btn-all");
    var tabLa = document.getElementById("tab-btn-life_areas");
    var tabSys = document.getElementById("tab-btn-system");
    if (tabPop) {
      tabPop.textContent = "Active Memories (" + totalMems + ")";
      tabPop.className = "seg-btn " + (filterTab === "populated" ? "active" : "");
    }
    if (tabAll) {
      tabAll.textContent = "All Categories (" + (lifeAreas.length + coreCats.length) + ")";
      tabAll.className = "seg-btn " + (filterTab === "all" ? "active" : "");
    }
    if (tabLa) {
      tabLa.textContent = "Life Areas (" + lifeAreas.length + "/8)";
      tabLa.className = "seg-btn " + (filterTab === "life_areas" ? "active" : "");
    }
    if (tabSys) {
      tabSys.className = "seg-btn " + (filterTab === "system" ? "active" : "");
    }

    var bodyEl = document.getElementById("dashboard-main-body");
    if (!bodyEl) return;

    if (filterTab === "system") {
      var sysHtml = '<div style="display:flex; flex-direction:column; gap:16px;">';
      sysHtml += '<div class="minimal-panel"><div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">';
      sysHtml += '<div><h3 style="font-size:15px; font-weight:600;">Always-Injected Core Profile Block</h3><div style="font-size:12.5px; color:var(--text-muted);">Injected into Claude Sonnet on every turn (max ~300 tokens, Redis-cached)</div></div>';
      sysHtml += '<span class="tag">v' + esc(state.core_profile.version) + ' · ' + esc(state.core_profile.built_from_count) + ' facts</span></div>';
      sysHtml += '<pre class="mono-block">' + esc(state.core_profile.summary || "(No core profile memories yet)") + '</pre></div>';

      sysHtml += '<div class="cards-grid"><div class="minimal-panel"><h3 style="font-size:15px; font-weight:600; margin-bottom:12px;">Privacy &amp; Memory Settings</h3>';
      sysHtml += '<div style="display:flex; flex-direction:column; gap:12px;">';
      sysHtml += '<div style="display:flex; justify-content:space-between; align-items:center;"><span><strong>Memory Enabled</strong></span><button type="button" class="btn btn-xs" data-action="toggle-memory-enabled">' + (state.settings.enabled ? "Enabled (Click to Opt Out)" : "Disabled (Click to Enable)") + '</button></div>';
      sysHtml += '<div style="display:flex; justify-content:space-between; align-items:center;"><span><strong>Anonymized Cohort Sharing (k&ge;10)</strong></span><button type="button" class="btn btn-xs" data-action="toggle-share-aggregate">' + (state.settings.share_aggregate ? "Shared" : "Private") + '</button></div>';
      sysHtml += '<div style="padding-top:12px; border-top:1px solid var(--border-subtle); display:flex; justify-content:space-between; align-items:center;"><span style="font-size:12px; color:var(--text-muted);">HMAC Tombstones: ' + esc(state.tombstone_count) + '</span><button type="button" class="btn btn-danger-ghost" data-action="delete-all-memories">Delete All Memories</button></div>';
      sysHtml += '</div></div>';

      var sup = state.superseded_history || [];
      sysHtml += '<div class="minimal-panel"><div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;"><h3 style="font-size:15px; font-weight:600;">Bi-Temporal Superseded History</h3><span class="tag">' + sup.length + ' retired</span></div>';
      if (sup.length === 0) {
        sysHtml += '<div style="font-size:13px; color:var(--text-muted);">No superseded memories yet. Updating a singleton slot preserves the prior version here with valid_to and retired_at timestamps.</div>';
      } else {
        sysHtml += '<ul class="memory-details-list">';
        for (var s = 0; s < sup.length; s++) {
          sysHtml += '<li class="memory-details-item" style="color:var(--text-secondary);"><span style="text-decoration:line-through;">' + esc(sup[s].statement) + '</span> <span class="tag">' + esc(sup[s].slot) + '</span></li>';
        }
        sysHtml += '</ul>';
      }
      sysHtml += '</div></div></div>';
      bodyEl.innerHTML = sysHtml;
      return;
    }

    // Check if we are in Layer 2 or Layer 3
    if (activeCategorySlug) {
      var activeCat = findCategoryBySlug(activeCategorySlug);
      if (!activeCat) {
        activeCategorySlug = null;
        activeSubcategorySlug = null;
      } else if (activeSubcategorySlug) {
        var activeSub = findSubcategoryBySlug(activeCat, activeSubcategorySlug);
        if (activeSub) {
          bodyEl.innerHTML = renderLayer3SubcategoryDetail(activeCat, activeSub);
          return;
        } else {
          activeSubcategorySlug = null;
          bodyEl.innerHTML = renderLayer2CategoryDetail(activeCat);
          return;
        }
      } else {
        bodyEl.innerHTML = renderLayer2CategoryDetail(activeCat);
        return;
      }
    }

    var q = (searchQuery || "").trim().toLowerCase();
    function matches(cat) {
      if (!q) return true;
      if ((cat.label_en || "").toLowerCase().indexOf(q) !== -1) return true;
      if ((cat.summary || "").toLowerCase().indexOf(q) !== -1) return true;
      var ms = cat.memories || [];
      for (var k = 0; k < ms.length; k++) {
        if ((ms[k].statement || "").toLowerCase().indexOf(q) !== -1) return true;
      }
      var subs = cat.subcategories || [];
      for (var u = 0; u < subs.length; u++) {
        if ((subs[u].label_en || "").toLowerCase().indexOf(q) !== -1) return true;
      }
      return false;
    }

    bodyEl.innerHTML = renderLayer1Overview(matches);
  }

  async function apiCall(url, method, payload) {
    var opts = { method: method || "GET", headers: {} };
    if (payload !== undefined) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(payload);
    }
    var res = await fetch(url, opts);
    return await res.json();
  }

  async function submitQuickMemoryInput(catSlug, subSlug) {
    var inp = document.getElementById("claude-memory-quick-input");
    var val = (inp && inp.value.trim()) || "";
    if (!val) return;
    if (inp) inp.value = "";

    var targetSlug = catSlug || activeCategorySlug || "preferences";
    var addData = await apiCall("/api/memories", "POST", {
      teacher_id: getTeacherId(),
      statement: val,
      category_slug: targetSlug,
      subcategory_slug: subSlug || activeSubcategorySlug || "",
      source: "stated",
      surface: "web",
      created_by: "teacher",
      explicit_consent_granted: true
    });
    if (addData && addData.state) {
      state = addData.state;
      renderDashboard();
      showMemoryToast("Saved to " + targetSlug.replace(/_/g, " "));
    }
  }

  async function sendChat(text) {
    var trimmed = (text || "").trim();
    if (!trimmed) return;
    var inputEl = document.getElementById("chat-message-input");
    if (inputEl) inputEl.value = "";

    messages.push({ id: "u-" + Date.now(), role: "user", content: trimmed });
    messages.push({ id: "thinking", role: "assistant", content: "Amal is thinking..." });
    renderChatStream();

    try {
      var data = await apiCall("/api/chat", "POST", {
        teacher_id: getTeacherId(),
        message: trimmed,
        history: chatHistory,
        surface: "web",
        product_area: "chat",
        anthropic_api_key: getAnthropicApiKey() || undefined,
        gemini_api_key: getGeminiApiKey() || undefined
      });
      messages = messages.filter(function(m) { return m.id !== "thinking"; });
      chatHistory.push({ role: "user", content: trimmed });
      chatHistory.push({ role: "assistant", content: data.reply || "" });
      messages.push({
        id: "a-" + Date.now(),
        role: "assistant",
        content: data.reply || data.error || "Done."
      });
      renderChatStream();
      if (data.state) {
        state = data.state;
        renderDashboard();
      }
      if (data.memory_stored || data.toast_message) {
        showMemoryToast(data.toast_message || "Amal learned something new about you. Discover in memories");
      }
    } catch (err) {
      messages = messages.filter(function(m) { return m.id !== "thinking"; });
      messages.push({ id: "err-" + Date.now(), role: "assistant", content: "Error communicating with Amal backend: " + String(err) });
      renderChatStream();
    }
  }

  initSavedKeys();

  document.addEventListener("click", async function(e) {
    var target = e.target;
    if (!target || !target.closest) return;

    var viewBtn = target.closest("[data-view-mode]");
    if (viewBtn) {
      e.preventDefault();
      viewMode = viewBtn.getAttribute("data-view-mode") || "split";
      updateViewModeUI();
      return;
    }

    var dispBtn = target.closest("[data-display-mode]");
    if (dispBtn) {
      e.preventDefault();
      memoryDisplayMode = dispBtn.getAttribute("data-display-mode") || "list";
      renderDashboard();
      return;
    }

    var tabBtn = target.closest("[data-filter-tab]");
    if (tabBtn) {
      e.preventDefault();
      filterTab = tabBtn.getAttribute("data-filter-tab") || "populated";
      if (filterTab === "system") {
        activeCategorySlug = null;
        activeSubcategorySlug = null;
      }
      renderDashboard();
      return;
    }

    var promptBtn = target.closest("[data-sample-prompt]");
    if (promptBtn) {
      e.preventDefault();
      var pText = promptBtn.getAttribute("data-sample-prompt") || "";
      await sendChat(pText);
      return;
    }

    var actBtn = target.closest("[data-action]");
    if (!actBtn) return;
    e.preventDefault();
    var action = actBtn.getAttribute("data-action");

    if (action === "open-category") {
      var slugToOpen = actBtn.getAttribute("data-slug");
      if (slugToOpen) {
        if (filterTab === "system") filterTab = "populated";
        activeCategorySlug = slugToOpen;
        activeSubcategorySlug = null;
        creatingSubcat = false;
        renderDashboard();
      }
      return;
    }

    if (action === "open-subcategory") {
      var pSlug = actBtn.getAttribute("data-cat-slug") || activeCategorySlug;
      var sSlug = actBtn.getAttribute("data-sub-slug");
      if (pSlug && sSlug) {
        if (filterTab === "system") filterTab = "populated";
        activeCategorySlug = pSlug;
        activeSubcategorySlug = sSlug;
        renderDashboard();
      }
      return;
    }

    if (action === "back-to-layer-1") {
      activeCategorySlug = null;
      activeSubcategorySlug = null;
      creatingSubcat = false;
      renderDashboard();
      return;
    }

    if (action === "toggle-import-memory") {
      showImportPanel = !showImportPanel;
      renderDashboard();
      return;
    }

    if (action === "copy-import-prompt") {
      var promptStr = 'Export all of your stored memories, preferences, teaching context, and ongoing topics about me as a bulleted list of concise third-person statements (one fact per line) so I can import them into Amal.';
      try {
        if (navigator.clipboard && navigator.clipboard.writeText) {
          await navigator.clipboard.writeText(promptStr);
        }
      } catch (err) {}
      actBtn.textContent = "Copied!";
      setTimeout(function() { actBtn.textContent = "Copy prompt"; }, 1400);
      return;
    }

    if (action === "submit-import-memories") {
      var ta = document.getElementById("import-memories-textarea");
      var rawText = (ta && ta.value.trim()) || "";
      if (!rawText) return;
      actBtn.textContent = "Importing...";
      var impRes = await apiCall("/api/memories/import", "POST", {
        teacher_id: getTeacherId(),
        raw_text: rawText,
        provider: "external_ai"
      });
      showImportPanel = false;
      if (impRes && impRes.state) {
        state = impRes.state;
        renderDashboard();
        showMemoryToast("Imported " + (impRes.imported_count || 0) + " memories into Amal.");
      }
      return;
    }

    if (action === "submit-quick-memory") {
      var cSlug = actBtn.getAttribute("data-cat-slug") || "";
      var subSlug = actBtn.getAttribute("data-sub-slug") || "";
      await submitQuickMemoryInput(cSlug, subSlug);
      return;
    }

    if (action === "toggle-new-subcategory") {
      creatingSubcat = !creatingSubcat;
      renderDashboard();
      return;
    }

    if (action === "create-subcategory-submit") {
      var parentId = actBtn.getAttribute("data-parent-id");
      var subEnEl = document.getElementById("new-subcat-en-input");
      var subSwEl = document.getElementById("new-subcat-sw-input");
      var subEn = (subEnEl && subEnEl.value.trim()) || "";
      var subSw = (subSwEl && subSwEl.value.trim()) || "";
      if (!subEn || !parentId) return;
      var subRes = await apiCall("/api/life-areas", "POST", {
        teacher_id: getTeacherId(),
        action: "create_subcategory",
        parent_id: parentId,
        label_en: subEn,
        label_sw: subSw
      });
      creatingSubcat = false;
      if (subRes && subRes.state) {
        state = subRes.state;
        if (subRes.category && subRes.category.slug) {
          activeSubcategorySlug = subRes.category.slug;
        }
        renderDashboard();
      }
      return;
    }

    if (action === "rename-subcategory") {
      var subId = actBtn.getAttribute("data-id");
      var oldSubLabel = actBtn.getAttribute("data-label") || "";
      var hEl = document.getElementById("layer3-detail-header");
      if (!hEl) return;
      hEl.innerHTML =
        '<div style="display:flex; gap:8px; width:100%; align-items:center;">' +
        '<input type="text" class="input" style="flex:1;" value="' + esc(oldSubLabel) + '" data-rename-sub-input="' + esc(subId) + '" />' +
        '<button type="button" class="btn btn-xs btn-primary" data-action="save-rename-subcategory" data-id="' + esc(subId) + '">Save</button>' +
        '<button type="button" class="btn btn-xs" data-action="cancel-inline">Cancel</button>' +
        '</div>';
      return;
    }

    if (action === "save-rename-subcategory") {
      var rSubId = actBtn.getAttribute("data-id");
      var rSubInp = document.querySelector('[data-rename-sub-input="' + rSubId + '"]');
      var nextSubLabel = (rSubInp && rSubInp.value.trim()) || "";
      if (!nextSubLabel) {
        renderDashboard();
        return;
      }
      var rSubData = await apiCall("/api/life-areas", "POST", {
        teacher_id: getTeacherId(),
        action: "rename_subcategory",
        category_id: rSubId,
        label_en: nextSubLabel
      });
      if (rSubData && rSubData.state) {
        state = rSubData.state;
        renderDashboard();
      }
      return;
    }

    if (action === "delete-subcategory") {
      var delSubId = actBtn.getAttribute("data-id");
      var delSubRes = await apiCall("/api/categories/" + delSubId + "/clear", "POST", {
        teacher_id: getTeacherId()
      });
      activeSubcategorySlug = null;
      if (delSubRes && delSubRes.state) {
        state = delSubRes.state;
        renderDashboard();
      }
      return;
    }

    if (action === "toggle-api-key") {
      showKeyBar = !showKeyBar;
      var bar = document.getElementById("api-key-drawer");
      if (bar) bar.style.display = showKeyBar ? "flex" : "none";
      actBtn.textContent = showKeyBar ? "Hide API Keys" : "API Keys";
      return;
    }

    if (action === "save-api-keys") {
      var antIn = document.getElementById("session-anthropic-key-input");
      var gemIn = document.getElementById("session-gemini-key-input");
      try {
        if (antIn) window.localStorage.setItem("amal_anthropic_api_key", antIn.value.trim());
        if (gemIn) window.localStorage.setItem("amal_gemini_api_key", gemIn.value.trim());
      } catch (err) {}
      actBtn.textContent = "Saved!";
      setTimeout(function() { actBtn.textContent = "Save Keys"; }, 1400);
      return;
    }

    if (action === "toast-discover-memories") {
      var tc = document.getElementById("amal-toast-container");
      if (tc) tc.innerHTML = "";
      if (viewMode === "chat") {
        viewMode = "memory";
        updateViewModeUI();
      }
      filterTab = "populated";
      renderDashboard();
      var dashEl = document.getElementById("memory-dashboard");
      if (dashEl && dashEl.scrollIntoView) {
        dashEl.scrollIntoView({ behavior: "smooth", block: "start" });
      }
      return;
    }

    if (action === "toast-dismiss") {
      var tc2 = document.getElementById("amal-toast-container");
      if (tc2) tc2.innerHTML = "";
      return;
    }

    if (action === "clear-chat") {
      chatHistory = [];
      messages = [messages[0]];
      renderChatStream();
      return;
    }

    if (action === "send-chat") {
      var inp = document.getElementById("chat-message-input");
      if (inp) await sendChat(inp.value);
      return;
    }

    if (action === "load-teacher") {
      var res = await apiCall("/api/memories?teacher_id=" + encodeURIComponent(getTeacherId()), "GET");
      if (res && res.teacher) {
        state = res;
        activeCategorySlug = null;
        activeSubcategorySlug = null;
        renderDashboard();
      }
      return;
    }

    if (action === "seed-demo") {
      actBtn.textContent = "Seeding...";
      try {
        var sData = await apiCall("/api/seed-demo", "POST", { teacher_id: getTeacherId() });
        if (sData && sData.state) {
          state = sData.state;
          activeCategorySlug = null;
          activeSubcategorySlug = null;
          renderDashboard();
        }
      } finally {
        actBtn.textContent = "Seed Demo";
      }
      return;
    }

    if (action === "run-dream") {
      actBtn.textContent = "Dreaming...";
      try {
        var dData = await apiCall("/api/dream", "POST", { teacher_id: getTeacherId() });
        if (dData && dData.state) {
          state = dData.state;
          renderDashboard();
        }
      } finally {
        actBtn.textContent = "Run Dreaming";
      }
      return;
    }

    if (action === "toggle-new-life-area") {
      creatingArea = !creatingArea;
      var formEl = document.getElementById("new-life-area-panel");
      if (formEl) formEl.style.display = creatingArea ? "flex" : "none";
      actBtn.textContent = creatingArea ? "Cancel" : "New Life Area";
      return;
    }

    if (action === "create-life-area-submit") {
      var enInp = document.getElementById("new-area-en-input");
      var swInp = document.getElementById("new-area-sw-input");
      var labelEn = (enInp && enInp.value.trim()) || "";
      var labelSw = (swInp && swInp.value.trim()) || "";
      if (!labelEn) return;
      var cData = await apiCall("/api/life-areas", "POST", {
        teacher_id: getTeacherId(),
        action: "create",
        label_en: labelEn,
        label_sw: labelSw
      });
      if (enInp) enInp.value = "";
      if (swInp) swInp.value = "";
      creatingArea = false;
      var fEl = document.getElementById("new-life-area-panel");
      if (fEl) fEl.style.display = "none";
      if (cData && cData.state) {
        state = cData.state;
        renderDashboard();
      }
      return;
    }

    if (action === "edit-memory") {
      var memId = actBtn.getAttribute("data-id");
      var curStmt = actBtn.getAttribute("data-statement") || "";
      var rowEl = actBtn.closest(".memory-bullet-row");
      if (!rowEl) return;
      rowEl.innerHTML =
        '<input type="text" class="input" style="flex:1;" value="' + esc(curStmt) + '" data-edit-input="' + esc(memId) + '" />' +
        '<div style="display:flex; gap:4px;">' +
        '<button type="button" class="btn btn-xs btn-primary" data-action="save-edit-memory" data-id="' + esc(memId) + '">Save</button>' +
        '<button type="button" class="btn btn-xs" data-action="cancel-inline">Cancel</button>' +
        '</div>';
      var editInp = rowEl.querySelector("input");
      if (editInp) editInp.focus();
      return;
    }

    if (action === "save-edit-memory") {
      var saveMemId = actBtn.getAttribute("data-id");
      var inpEl = document.querySelector('[data-edit-input="' + saveMemId + '"]');
      var nextStmt = (inpEl && inpEl.value.trim()) || "";
      if (!nextStmt) {
        renderDashboard();
        return;
      }
      var eData = await apiCall("/api/memories/" + saveMemId, "PATCH", {
        teacher_id: getTeacherId(),
        statement: nextStmt
      });
      if (eData && eData.state) {
        state = eData.state;
        renderDashboard();
      }
      return;
    }

    if (action === "cancel-inline") {
      renderDashboard();
      return;
    }

    if (action === "delete-memory") {
      var delId = actBtn.getAttribute("data-id");
      var delData = await apiCall("/api/memories/" + delId + "?teacher_id=" + encodeURIComponent(getTeacherId()), "DELETE");
      if (delData && delData.state) {
        state = delData.state;
        renderDashboard();
      }
      return;
    }

    if (action === "add-detail") {
      var catSlug = actBtn.getAttribute("data-slug");
      var footerEl = actBtn.closest(".memory-card-footer");
      if (!footerEl) return;
      footerEl.innerHTML =
        '<div style="display:flex; gap:6px; width:100%; align-items:center;">' +
        '<input type="text" class="input" style="flex:1;" placeholder="Add detail (e.g. Built an Anki card creator skill)" data-add-input="' + esc(catSlug) + '" />' +
        '<button type="button" class="btn btn-xs btn-primary" data-action="save-add-detail" data-slug="' + esc(catSlug) + '">Save</button>' +
        '<button type="button" class="btn btn-xs" data-action="cancel-inline">Cancel</button>' +
        '</div>';
      var addInp = footerEl.querySelector("input");
      if (addInp) addInp.focus();
      return;
    }

    if (action === "save-add-detail") {
      var saveSlug = actBtn.getAttribute("data-slug");
      var addInputEl = document.querySelector('[data-add-input="' + saveSlug + '"]');
      var addedStmt = (addInputEl && addInputEl.value.trim()) || "";
      if (!addedStmt) {
        renderDashboard();
        return;
      }
      var addData = await apiCall("/api/memories", "POST", {
        teacher_id: getTeacherId(),
        statement: addedStmt,
        category_slug: saveSlug,
        source: "stated",
        surface: "web",
        created_by: "teacher",
        explicit_consent_granted: true
      });
      if (addData && addData.state) {
        state = addData.state;
        renderDashboard();
      }
      return;
    }

    if (action === "delete-category") {
      var catId = actBtn.getAttribute("data-id");
      var isLa = actBtn.getAttribute("data-life-area") === "1";
      var resCat = isLa
        ? await apiCall("/api/life-areas", "POST", { teacher_id: getTeacherId(), action: "delete", category_id: catId })
        : await apiCall("/api/categories/" + catId + "/clear", "POST", { teacher_id: getTeacherId() });
      if (isLa) {
        activeCategorySlug = null;
        activeSubcategorySlug = null;
      }
      if (resCat && resCat.state) {
        state = resCat.state;
        renderDashboard();
      }
      return;
    }

    if (action === "rename-life-area") {
      var laId = actBtn.getAttribute("data-id");
      var oldName = actBtn.getAttribute("data-label") || "";
      var headerEl = actBtn.closest(".memory-card-header") || document.getElementById("layer2-detail-header");
      if (!headerEl) return;
      headerEl.innerHTML =
        '<div style="display:flex; gap:6px; width:100%; align-items:center;">' +
        '<input type="text" class="input" style="flex:1;" value="' + esc(oldName) + '" data-rename-input="' + esc(laId) + '" />' +
        '<button type="button" class="btn btn-xs btn-primary" data-action="save-rename-life-area" data-id="' + esc(laId) + '">Save</button>' +
        '<button type="button" class="btn btn-xs" data-action="cancel-inline">Cancel</button>' +
        '</div>';
      var renInp = headerEl.querySelector("input");
      if (renInp) renInp.focus();
      return;
    }

    if (action === "save-rename-life-area") {
      var saveLaId = actBtn.getAttribute("data-id");
      var renInputEl = document.querySelector('[data-rename-input="' + saveLaId + '"]');
      var newName = (renInputEl && renInputEl.value.trim()) || "";
      if (!newName) {
        renderDashboard();
        return;
      }
      var renData = await apiCall("/api/life-areas", "POST", {
        teacher_id: getTeacherId(),
        action: "rename",
        category_id: saveLaId,
        label_en: newName
      });
      if (renData && renData.state) {
        state = renData.state;
        renderDashboard();
      }
      return;
    }

    if (action === "restore-life-area") {
      var rId = actBtn.getAttribute("data-id");
      var rData = await apiCall("/api/life-areas", "POST", {
        teacher_id: getTeacherId(),
        action: "restore",
        category_id: rId
      });
      if (rData && rData.state) {
        state = rData.state;
        renderDashboard();
      }
      return;
    }

    if (action === "resolve-consent") {
      var cId = actBtn.getAttribute("data-id");
      var ans = actBtn.getAttribute("data-ans") || "no";
      var conData = await apiCall("/api/consent/" + cId, "POST", {
        teacher_id: getTeacherId(),
        answer: ans
      });
      if (conData && conData.state) {
        state = conData.state;
        renderDashboard();
      }
      return;
    }

    if (action === "notif-action") {
      var nId = actBtn.getAttribute("data-id");
      var nAct = actBtn.getAttribute("data-act") || "kept";
      var nData = await apiCall("/api/notifications/" + nId + "/action", "POST", {
        teacher_id: getTeacherId(),
        action: nAct
      });
      if (nData && nData.state) {
        state = nData.state;
        renderDashboard();
      }
      return;
    }

    if (action === "undo-changeset") {
      var csId = actBtn.getAttribute("data-id");
      var uData = await apiCall("/api/taxonomy/undo/" + csId, "POST", {
        teacher_id: getTeacherId()
      });
      if (uData && uData.state) {
        state = uData.state;
        renderDashboard();
      }
      return;
    }

    if (action === "toggle-memory-enabled") {
      var nextEnabled = !(state && state.settings && state.settings.enabled);
      var set1 = await apiCall("/api/settings", "POST", {
        teacher_id: getTeacherId(),
        enabled: nextEnabled
      });
      if (set1 && set1.state) {
        state = set1.state;
        renderDashboard();
      }
      return;
    }

    if (action === "toggle-share-aggregate") {
      var nextShare = !(state && state.settings && state.settings.share_aggregate);
      var set2 = await apiCall("/api/settings", "POST", {
        teacher_id: getTeacherId(),
        share_aggregate: nextShare
      });
      if (set2 && set2.state) {
        state = set2.state;
        renderDashboard();
      }
      return;
    }

    if (action === "delete-all-memories") {
      var daData = await apiCall("/api/memories/delete-all", "POST", {
        teacher_id: getTeacherId()
      });
      if (daData && daData.state) {
        state = daData.state;
        activeCategorySlug = null;
        activeSubcategorySlug = null;
        renderDashboard();
      }
      return;
    }
  });

  document.addEventListener("keydown", function(e) {
    if (e.key === "Enter" && e.target && e.target.id === "chat-message-input") {
      e.preventDefault();
      sendChat(e.target.value);
    }
    if (e.key === "Enter" && e.target && e.target.id === "claude-memory-quick-input") {
      e.preventDefault();
      var cSlug = e.target.getAttribute("data-cat-slug") || "";
      var sSlug = e.target.getAttribute("data-sub-slug") || "";
      submitQuickMemoryInput(cSlug, sSlug);
    }
    if (e.key === "Enter" && e.target && e.target.id === "teacher-id-input") {
      e.preventDefault();
      apiCall("/api/memories?teacher_id=" + encodeURIComponent(getTeacherId()), "GET").then(function(res) {
        if (res && res.teacher) {
          state = res;
          activeCategorySlug = null;
          activeSubcategorySlug = null;
          renderDashboard();
        }
      });
    }
  });

  document.addEventListener("input", function(e) {
    if (e.target && e.target.id === "category-search-input") {
      searchQuery = e.target.value || "";
      renderDashboard();
    }
  });
})();
`;

export default function ClientWorkspace({ initialState }: ClientWorkspaceProps) {
  const teacherId = initialState.teacher?.teacher_id || "teacher-wambui-ke";
  const chatModel =
    initialState.llm_status?.chat_model || "claude-sonnet-4-20250514";
  const decisionModel =
    initialState.llm_status?.decision_model ||
    initialState.llm_status?.extraction_model ||
    "gemini-2.5-flash";
  const isLiveKey = Boolean(
    initialState.llm_status?.anthropic_key_configured ||
      initialState.llm_status?.gemini_key_configured ||
      initialState.llm_status?.api_key_configured
  );

  const totalSavedMemories =
    initialState.life_areas.reduce((acc, c) => acc + c.memories.length, 0) +
    initialState.core_categories.reduce((acc, c) => acc + c.memories.length, 0);

  const youSlugSet = new Set([
    "preferences",
    "profile",
    "teaching_context",
    "classroom",
    "people",
    "wellbeing",
    "named_learners",
  ]);

  const allPopulatedCategories: CategoryCardData[] = [
    ...initialState.core_categories.filter((c) => c.memories.length > 0),
    ...initialState.life_areas,
  ];

  const youCategories = allPopulatedCategories.filter(
    (c) => (c.section || (youSlugSet.has(c.slug) ? "you" : "topics")) === "you"
  );
  const topicCategories = allPopulatedCategories.filter(
    (c) =>
      (c.section || (youSlugSet.has(c.slug) ? "you" : "topics")) === "topics"
  );

  const serializedState = JSON.stringify(initialState).replace(/</g, "\\u003c");

  return (
    <div>
      {/* Minimalist Top Bar */}
      <header className="topbar">
        <div className="brand-group">
          <div>
            <h1 className="brand-title">Amal</h1>
            <div className="brand-subtitle" id="brand-subtitle-text">
              {initialState.teacher
                ? `${initialState.teacher.display_name} · ${initialState.teacher.curriculum}`
                : "Teaching Assistant & Categorical Memory"}
            </div>
          </div>

          <span className="status-pill">
            <span className={`status-dot ${isLiveKey ? "" : "offline"}`} />
            Chat: {chatModel} · Decision: {decisionModel}
          </span>
        </div>

        {/* View Mode Switcher */}
        <div className="segmented-tabs" role="tablist" aria-label="Workspace view">
          <button
            type="button"
            className="seg-btn active"
            data-view-mode="split"
          >
            Split View
          </button>
          <button
            type="button"
            className="seg-btn"
            data-view-mode="memory"
          >
            Memories
          </button>
          <button
            type="button"
            className="seg-btn"
            data-view-mode="chat"
          >
            Chat
          </button>
        </div>

        {/* Right Controls */}
        <div className="topbar-controls">
          <div style={{ display: "flex", gap: "6px", alignItems: "center" }}>
            <input
              id="teacher-id-input"
              type="text"
              className="input"
              style={{ width: "155px" }}
              defaultValue={teacherId}
              placeholder="Teacher ID"
            />
            <button
              type="button"
              className="btn"
              data-action="load-teacher"
            >
              Load
            </button>
          </div>

          <button
            id="seed-demo-btn"
            type="button"
            className="btn"
            data-action="seed-demo"
          >
            Seed Demo
          </button>

          <button
            id="run-dream-btn"
            type="button"
            className="btn btn-accent"
            data-action="run-dream"
          >
            Run Dreaming
          </button>

          <a
            id="export-json-link"
            className="btn"
            href={`/api/memories/export?teacher_id=${encodeURIComponent(
              teacherId
            )}`}
          >
            Export JSON
          </a>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="workspace">
        <div className="workspace-split" id="workspace-layout">
          {/* LEFT: Chat Column */}
          <div id="chat-column-wrap">
            <section
              className="chat-shell"
              id="amal-chat-panel"
              aria-label="Chat with Amal"
            >
              <div className="chat-header">
                <div>
                  <div className="chat-header-title">
                    Amal Teaching Assistant
                  </div>
                  <div className="chat-header-sub">
                    Agent: {chatModel} · Memory Decision: {decisionModel}
                  </div>
                </div>
                <div style={{ display: "flex", gap: "6px" }}>
                  <button
                    type="button"
                    className="btn btn-xs"
                    data-action="toggle-api-key"
                  >
                    Hide API Keys
                  </button>
                  <button
                    type="button"
                    className="btn btn-xs"
                    data-action="clear-chat"
                  >
                    Clear
                  </button>
                </div>
              </div>

              <div
                id="api-key-drawer"
                className="api-key-bar"
                style={{
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "stretch",
                  gap: "6px",
                }}
              >
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "8px",
                  }}
                >
                  <span
                    style={{
                      color: "var(--text-secondary)",
                      whiteSpace: "nowrap",
                      width: "110px",
                      fontSize: "11.5px",
                      fontWeight: 500,
                    }}
                  >
                    Anthropic Key:
                  </span>
                  <input
                    id="session-anthropic-key-input"
                    type="password"
                    className="input"
                    style={{ flex: 1, padding: "4px 8px", fontSize: "12px" }}
                    placeholder="sk-ant-... (Claude Sonnet chat — or set ANTHROPIC_API_KEY in .env)"
                  />
                </div>
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "8px",
                  }}
                >
                  <span
                    style={{
                      color: "var(--text-secondary)",
                      whiteSpace: "nowrap",
                      width: "110px",
                      fontSize: "11.5px",
                      fontWeight: 500,
                    }}
                  >
                    Gemini Key:
                  </span>
                  <input
                    id="session-gemini-key-input"
                    type="password"
                    className="input"
                    style={{ flex: 1, padding: "4px 8px", fontSize: "12px" }}
                    placeholder="AIzaSy... (Gemini Memory Decision API — or set GEMINI_API_KEY in .env)"
                  />
                  <button
                    type="button"
                    className="btn btn-xs btn-primary"
                    data-action="save-api-keys"
                  >
                    Save Keys
                  </button>
                </div>
              </div>

              <div className="chat-stream" id="chat-stream-container">
                <div className="chat-bubble-wrap assistant">
                  <div className="chat-bubble assistant">
                    Habari Mwalimu! I am Amal, your teaching assistant. Ask me
                    anything or share something about your classroom and work.
                  </div>
                </div>
              </div>

              <div className="chat-prompts-strip" aria-label="Sample prompts">
                {SAMPLE_PROMPTS.map((prompt, idx) => (
                  <button
                    key={idx}
                    type="button"
                    className="prompt-pill"
                    data-sample-prompt={prompt}
                  >
                    {prompt.length > 56 ? `${prompt.slice(0, 56)}...` : prompt}
                  </button>
                ))}
              </div>

              <div className="chat-composer">
                <input
                  id="chat-message-input"
                  type="text"
                  className="chat-composer-input"
                  placeholder="Message Amal or share something about your classroom..."
                />
                <button
                  id="chat-send-button"
                  type="button"
                  className="btn btn-primary"
                  data-action="send-chat"
                >
                  Send
                </button>
              </div>
            </section>
          </div>

          {/* RIGHT: Memory Dashboard Column */}
          <div id="dashboard-column-wrap">
            <div className="dashboard-col" id="memory-dashboard">
              {/* Alerts Stack */}
              <div
                id="alerts-stack-container"
                className="alert-stack"
                style={{
                  display:
                    initialState.pending_consents.length > 0 ? "flex" : "none",
                }}
              >
                {initialState.pending_consents.map((c) => (
                  <div key={c.consent_id} className="notice-bar consent">
                    <div>
                      <div
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: "8px",
                        }}
                      >
                        <span className="tag consent">{c.category_label}</span>
                        <strong style={{ fontSize: "13.5px" }}>
                          Amal would like to remember this. Keep it?
                        </strong>
                      </div>
                      <div style={{ marginTop: "4px", fontSize: "13.5px" }}>
                        &ldquo;{c.statement}&rdquo;
                      </div>
                      <div className="notice-meta">
                        Excluded from retrieval until approved · {c.prompt_text}
                      </div>
                    </div>
                    <div
                      style={{ display: "flex", gap: "6px", flexShrink: 0 }}
                    >
                      <button
                        type="button"
                        className="btn btn-xs btn-primary"
                        data-action="resolve-consent"
                        data-id={c.consent_id}
                        data-ans="yes"
                      >
                        Yes, Keep
                      </button>
                      <button
                        type="button"
                        className="btn btn-xs btn-danger-ghost"
                        data-action="resolve-consent"
                        data-id={c.consent_id}
                        data-ans="no"
                      >
                        No, Delete
                      </button>
                    </div>
                  </div>
                ))}
              </div>

              {/* Filter, View Mode (List / Cards) & Search Toolbar */}
              <div className="dashboard-toolbar">
                <div className="segmented-tabs">
                  <button
                    id="tab-btn-populated"
                    type="button"
                    className="seg-btn active"
                    data-filter-tab="populated"
                  >
                    Active Memories ({totalSavedMemories})
                  </button>
                  <button
                    id="tab-btn-all"
                    type="button"
                    className="seg-btn"
                    data-filter-tab="all"
                  >
                    All Categories (
                    {initialState.life_areas.length +
                      initialState.core_categories.length}
                    )
                  </button>
                  <button
                    id="tab-btn-life_areas"
                    type="button"
                    className="seg-btn"
                    data-filter-tab="life_areas"
                  >
                    Life Areas ({initialState.life_areas.length}/8)
                  </button>
                  <button
                    id="tab-btn-system"
                    type="button"
                    className="seg-btn"
                    data-filter-tab="system"
                  >
                    Core Profile &amp; Settings
                  </button>
                </div>

                <div
                  style={{ display: "flex", gap: "8px", alignItems: "center", flexWrap: "wrap" }}
                >
                  {/* List vs Cards Toggle */}
                  <div
                    className="segmented-tabs"
                    role="group"
                    aria-label="Memory display layout"
                  >
                    <button
                      type="button"
                      className="seg-btn active"
                      data-display-mode="list"
                    >
                      List
                    </button>
                    <button
                      type="button"
                      className="seg-btn"
                      data-display-mode="cards"
                    >
                      Cards
                    </button>
                  </div>

                  <input
                    id="category-search-input"
                    type="text"
                    className="input"
                    placeholder="Filter categories or memories..."
                    style={{ width: "200px" }}
                  />
                  <button
                    type="button"
                    className="btn"
                    data-action="toggle-new-life-area"
                  >
                    New Life Area
                  </button>
                </div>
              </div>

              {/* New Life Area Form */}
              <div
                id="new-life-area-panel"
                className="minimal-panel"
                style={{
                  display: "none",
                  gap: "10px",
                  alignItems: "center",
                  flexWrap: "wrap",
                }}
              >
                <strong style={{ fontSize: "13px" }}>Create Life Area:</strong>
                <input
                  id="new-area-en-input"
                  type="text"
                  className="input"
                  placeholder="Category title (e.g. AI Tooling)"
                />
                <input
                  id="new-area-sw-input"
                  type="text"
                  className="input"
                  placeholder="Swahili label (optional, e.g. Zana za AI)"
                />
                <button
                  type="button"
                  className="btn btn-primary"
                  data-action="create-life-area-submit"
                >
                  Create
                </button>
              </div>

              {/* Main Memory Body (SSR defaults to Claude-style Layer 1 List View) */}
              <div id="dashboard-main-body">
                <div className="claude-memory-shell">
                  <div className="claude-breadcrumb-bar">
                    <span style={{ color: "var(--text-secondary)" }}>
                      &larr; Your Amal
                    </span>
                    <span className="sep">/</span>
                    <span className="current">Memory</span>
                    <span className="tag" style={{ marginLeft: "auto" }}>
                      Layer 1 of 3 &middot; You &amp; Topics
                    </span>
                  </div>

                  <div className="claude-import-banner">
                    <div className="claude-import-banner-text">
                      <div className="claude-import-banner-title">
                        Import memory from other AI providers
                      </div>
                      <div className="claude-import-banner-sub">
                        Bring relevant context and data from another AI provider
                        to Amal. We&apos;ll provide a prompt you can use to
                        fetch the memory from your other account.
                      </div>
                    </div>
                    <button
                      type="button"
                      className="btn"
                      data-action="toggle-import-memory"
                    >
                      Start import
                    </button>
                  </div>

                  {/* You Section */}
                  <div className="claude-section-block">
                    <h3 className="claude-section-heading">You</h3>
                    <div className="claude-list-table" role="list">
                      {youCategories.map((cat) => (
                        <div
                          key={cat.id}
                          className="claude-list-row"
                          role="listitem"
                          tabIndex={0}
                          data-action="open-category"
                          data-slug={cat.slug}
                        >
                          <div className="claude-list-title">
                            {cat.label_en}
                          </div>
                          <div className="claude-list-summary">
                            {cat.summary}
                          </div>
                          <div className="claude-list-date">
                            {cat.last_updated_short ||
                              `Updated ${cat.last_updated}`}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Topics Section */}
                  <div className="claude-section-block">
                    <h3 className="claude-section-heading">Topics</h3>
                    <div className="claude-list-table" role="list">
                      {topicCategories.map((cat) => (
                        <div
                          key={cat.id}
                          className="claude-list-row"
                          role="listitem"
                          tabIndex={0}
                          data-action="open-category"
                          data-slug={cat.slug}
                        >
                          <div className="claude-list-title">
                            {cat.label_en}
                          </div>
                          <div className="claude-list-summary">
                            {cat.summary}
                          </div>
                          <div className="claude-list-date">
                            {cat.last_updated_short ||
                              `Updated ${cat.last_updated}`}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Bottom Pill Input Bar */}
                  <div className="claude-bottom-input-wrap">
                    <div className="claude-bottom-input-bar">
                      <input
                        type="text"
                        id="claude-memory-quick-input"
                        className="claude-bottom-input"
                        placeholder="My dog's name is Beans"
                        data-cat-slug=""
                        data-sub-slug=""
                      />
                      <button
                        type="button"
                        className="claude-up-btn"
                        data-action="submit-quick-memory"
                        data-cat-slug=""
                        data-sub-slug=""
                        title="Save to memory"
                        aria-label="Save to memory"
                      >
                        &uarr;
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </main>

      {/* Floating Toast Notification Container */}
      <div id="amal-toast-container" className="amal-toast-container" />

      {/* Self-contained inline state + event-delegated runtime so buttons work even in single-document preview iframes */}
      <script
        dangerouslySetInnerHTML={{
          __html: `window.__AMAL_INITIAL_STATE__ = ${serializedState};\n${INLINE_RUNTIME_SCRIPT}`,
        }}
      />
    </div>
  );
}
