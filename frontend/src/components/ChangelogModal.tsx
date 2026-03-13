"use client";

import React, { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { X, Zap, Ship, Download, Shield, Bug, Heart } from "lucide-react";

const CURRENT_VERSION = "0.9";
const STORAGE_KEY = `shadowbroker_changelog_v${CURRENT_VERSION}`;

const NEW_FEATURES = [
    {
        icon: <Download size={14} className="text-cyan-400" />,
        title: "In-App Auto-Updater",
        desc: "One-click updates directly from the dashboard. Downloads the latest release, backs up your files, extracts over the project, and auto-restarts. Manual download fallback included if anything goes wrong.",
        color: "cyan",
    },
    {
        icon: <Ship size={14} className="text-blue-400" />,
        title: "Granular Ship Layer Controls",
        desc: "Ships split into 4 independent toggles: Military/Carriers, Cargo/Tankers, Civilian Vessels, and Cruise/Passenger. Each shows its own live count in the sidebar.",
        color: "blue",
    },
    {
        icon: <Shield size={14} className="text-green-400" />,
        title: "Stable Entity Selection",
        desc: "Ship and flight markers now use MMSI/callsign IDs instead of volatile array indices. Selecting a ship or plane stays locked on even when data refreshes every 60 seconds.",
        color: "green",
    },
    {
        icon: <X size={14} className="text-red-400" />,
        title: "Dismissible Threat Alerts",
        desc: "Click the X on any threat alert bubble to dismiss it for the session. Uses stable content hashing so dismissed alerts stay hidden across 60-second data refreshes.",
        color: "red",
    },
    {
        icon: <Zap size={14} className="text-yellow-400" />,
        title: "Faster Data Loading",
        desc: "GDELT military incidents now load instantly with background title enrichment instead of blocking for 2+ minutes. Eliminated duplicate startup fetch jobs for faster boot.",
        color: "yellow",
    },
];

const BUG_FIXES = [
    "Removed viewport bbox filtering that caused 20-second delays when panning between regions",
    "Fixed carrier tracker crash on GDELT 429/TypeError responses",
    "Removed fake intelligence assessment generator — all data is now real OSINT only",
    "Docker healthcheck start_period increased to 90s to prevent false-negative restarts during data preload",
    "ETag collision fix — full payload hash instead of first 256 chars",
    "Concurrent /api/refresh guard prevents duplicate data fetches",
];

const CONTRIBUTORS = [
    { name: "@imqdcr", desc: "Ship toggle split into 4 categories + stable MMSI/callsign entity IDs for map markers" },
    { name: "@csysp", desc: "Dismissible threat alert bubbles with stable content hashing + stopPropagation crash fix", pr: "#48" },
    { name: "@suranyami", desc: "Parallel multi-arch Docker builds (11min → 3min) + runtime BACKEND_URL fix", pr: "#35, #44" },
];

export function useChangelog() {
    const [show, setShow] = useState(false);
    useEffect(() => {
        const seen = localStorage.getItem(STORAGE_KEY);
        if (!seen) setShow(true);
    }, []);
    return { showChangelog: show, setShowChangelog: setShow };
}

interface ChangelogModalProps {
    onClose: () => void;
}

const ChangelogModal = React.memo(function ChangelogModal({ onClose }: ChangelogModalProps) {
    const handleDismiss = () => {
        localStorage.setItem(STORAGE_KEY, "true");
        onClose();
    };

    return (
        <AnimatePresence>
            <motion.div
                key="changelog-backdrop"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="fixed inset-0 bg-black/80 backdrop-blur-sm z-[10000]"
                onClick={handleDismiss}
            />
            <motion.div
                key="changelog-modal"
                initial={{ opacity: 0, scale: 0.9, y: 20 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.9, y: 20 }}
                transition={{ type: "spring", damping: 25, stiffness: 300 }}
                className="fixed inset-0 z-[10001] flex items-center justify-center pointer-events-none"
            >
                <div
                    className="w-[560px] max-h-[85vh] bg-[var(--bg-secondary)]/98 border border-cyan-900/50 rounded-xl shadow-[0_0_80px_rgba(0,200,255,0.08)] pointer-events-auto flex flex-col overflow-hidden"
                    onClick={(e) => e.stopPropagation()}
                >
                    {/* Header */}
                    <div className="p-5 pb-3 border-b border-[var(--border-primary)]/80">
                        <div className="flex items-center justify-between">
                            <div>
                                <div className="flex items-center gap-3">
                                    <div className="px-2 py-1 rounded bg-cyan-500/15 border border-cyan-500/30 text-[10px] font-mono font-bold text-cyan-400 tracking-widest">
                                        v{CURRENT_VERSION}
                                    </div>
                                    <h2 className="text-sm font-bold tracking-[0.15em] text-[var(--text-primary)] font-mono">
                                        WHAT&apos;S NEW
                                    </h2>
                                </div>
                                <p className="text-[9px] text-[var(--text-muted)] font-mono tracking-widest mt-1">
                                    SHADOWBROKER INTELLIGENCE PLATFORM UPDATE
                                </p>
                            </div>
                            <button
                                onClick={handleDismiss}
                                className="w-8 h-8 rounded-lg border border-[var(--border-primary)] hover:border-red-500/50 flex items-center justify-center text-[var(--text-muted)] hover:text-red-400 transition-all hover:bg-red-950/20"
                            >
                                <X size={14} />
                            </button>
                        </div>
                    </div>

                    {/* Content */}
                    <div className="flex-1 overflow-y-auto styled-scrollbar p-5 space-y-4">
                        {/* New Features */}
                        <div>
                            <div className="text-[9px] font-mono tracking-[0.2em] text-cyan-400 font-bold mb-3 flex items-center gap-2">
                                <div className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse" />
                                NEW CAPABILITIES
                            </div>
                            <div className="space-y-2">
                                {NEW_FEATURES.map((f) => (
                                    <div key={f.title} className="flex items-start gap-3 p-3 rounded-lg border border-[var(--border-primary)]/50 bg-[var(--bg-primary)]/30 hover:border-[var(--border-secondary)] transition-colors">
                                        <div className="mt-0.5 flex-shrink-0">{f.icon}</div>
                                        <div>
                                            <div className="text-[10px] font-mono text-[var(--text-primary)] font-bold">{f.title}</div>
                                            <div className="text-[9px] font-mono text-[var(--text-muted)] leading-relaxed mt-0.5">{f.desc}</div>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>

                        {/* Bug Fixes */}
                        <div>
                            <div className="text-[9px] font-mono tracking-[0.2em] text-green-400 font-bold mb-3 flex items-center gap-2">
                                <Bug size={10} className="text-green-400" />
                                FIXES &amp; IMPROVEMENTS
                            </div>
                            <div className="space-y-1.5">
                                {BUG_FIXES.map((fix, i) => (
                                    <div key={i} className="flex items-start gap-2 px-3 py-1.5">
                                        <span className="text-green-500 text-[10px] mt-0.5 flex-shrink-0">+</span>
                                        <span className="text-[9px] font-mono text-[var(--text-secondary)] leading-relaxed">{fix}</span>
                                    </div>
                                ))}
                            </div>
                        </div>

                        {/* Contributors */}
                        <div>
                            <div className="text-[9px] font-mono tracking-[0.2em] text-pink-400 font-bold mb-3 flex items-center gap-2">
                                <Heart size={10} className="text-pink-400" />
                                COMMUNITY CONTRIBUTORS
                            </div>
                            <div className="space-y-1.5">
                                {CONTRIBUTORS.map((c, i) => (
                                    <div key={i} className="flex items-start gap-2 px-3 py-2 rounded-lg border border-pink-500/20 bg-pink-500/5">
                                        <span className="text-pink-400 text-[10px] mt-0.5 flex-shrink-0">&hearts;</span>
                                        <div>
                                            <span className="text-[10px] font-mono text-pink-300 font-bold">{c.name}</span>
                                            <span className="text-[9px] font-mono text-[var(--text-muted)]"> — {c.desc}</span>
                                            <span className="text-[8px] font-mono text-[var(--text-muted)]"> (PR {c.pr})</span>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    </div>

                    {/* Footer */}
                    <div className="p-4 border-t border-[var(--border-primary)]/80 flex items-center justify-center">
                        <button
                            onClick={handleDismiss}
                            className="px-8 py-2.5 rounded-lg bg-cyan-500/15 border border-cyan-500/40 text-cyan-400 hover:bg-cyan-500/25 text-[10px] font-mono tracking-[0.2em] transition-all"
                        >
                            ACKNOWLEDGED
                        </button>
                    </div>
                </div>
            </motion.div>
        </AnimatePresence>
    );
});

export default ChangelogModal;
