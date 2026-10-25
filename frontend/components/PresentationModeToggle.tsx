"use client";

import { useState, useEffect } from "react";

export function PresentationModeToggle() {
    const [isJudgeMode, setIsJudgeMode] = useState(false);

    useEffect(() => {
        const stored = localStorage.getItem("judge_mode");
        if (stored === "true") {
            setIsJudgeMode(true);
            document.body.classList.add("judge-mode");
        }
    }, []);

    const toggleMode = () => {
        const next = !isJudgeMode;
        setIsJudgeMode(next);
        localStorage.setItem("judge_mode", String(next));
        if (next) {
            document.body.classList.add("judge-mode");
        } else {
            document.body.classList.remove("judge-mode");
        }
    };

    return (
        <div className="fixed bottom-4 right-4 z-50 flex flex-col items-end gap-2">
            {isJudgeMode && (
                <div className="bg-[#76B900] text-black px-4 py-2 rounded-full shadow-lg font-bold animate-pulse text-sm border-2 border-black">
                    🏆 Global AI Hackathon Demo Mode Active
                </div>
            )}
            <button
                onClick={toggleMode}
                className="opacity-20 hover:opacity-100 bg-black text-white text-xs px-2 py-1 rounded transition-opacity cursor-pointer border border-white"
            >
                {isJudgeMode ? "Disable Judge Mode" : "Enable Judge Mode"}
            </button>
        </div>
    );
}
