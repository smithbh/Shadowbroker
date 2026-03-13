"use client";

import React, { createContext, useContext } from "react";

interface DashboardDataContextValue {
    data: any;
    selectedEntity: { id: string | number; type: string; extra?: any } | null;
    setSelectedEntity: (entity: { id: string | number; type: string; extra?: any } | null) => void;
}

const DashboardDataContext = createContext<DashboardDataContextValue | null>(null);

export function DashboardDataProvider({
    data,
    selectedEntity,
    setSelectedEntity,
    children,
}: DashboardDataContextValue & { children: React.ReactNode }) {
    return (
        <DashboardDataContext.Provider value={{ data, selectedEntity, setSelectedEntity }}>
            {children}
        </DashboardDataContext.Provider>
    );
}

export function useDashboardData(): DashboardDataContextValue {
    const ctx = useContext(DashboardDataContext);
    if (!ctx) throw new Error("useDashboardData must be used within DashboardDataProvider");
    return ctx;
}
