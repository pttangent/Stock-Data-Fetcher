import { useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import Home from "@/pages/home";
import Symbols from "@/pages/symbols";

const queryClient = new QueryClient();

function AppContent() {
  const [activeTab, setActiveTab] = useState<"stock" | "symbols">("stock");
  const [pendingSymbolQuery, setPendingSymbolQuery] = useState<string | null>(null);

  const handleSymbolClick = (sym: string) => {
    setPendingSymbolQuery(sym);
    setActiveTab("stock");
  };

  return (
    <div className="min-h-screen bg-background text-foreground font-mono flex flex-col">
      <nav className="border-b border-border flex shrink-0">
        <button
          onClick={() => setActiveTab("stock")}
          className={`flex-1 py-4 text-center text-sm font-bold tracking-widest uppercase transition-colors border-b-2 ${
            activeTab === "stock"
              ? "border-primary text-primary bg-muted/10"
              : "border-transparent text-muted-foreground hover:text-foreground hover:bg-muted/5"
          }`}
        >
          個股查詢 / STOCK
        </button>
        <div className="w-px bg-border"></div>
        <button
          onClick={() => setActiveTab("symbols")}
          className={`flex-1 py-4 text-center text-sm font-bold tracking-widest uppercase transition-colors border-b-2 ${
            activeTab === "symbols"
              ? "border-primary text-primary bg-muted/10"
              : "border-transparent text-muted-foreground hover:text-foreground hover:bg-muted/5"
          }`}
        >
          清單查詢 / SYMBOLS
        </button>
      </nav>
      <div className="flex-1">
        {activeTab === "stock" ? (
          <Home
            pendingSymbolQuery={pendingSymbolQuery}
            onPendingQueryHandled={() => setPendingSymbolQuery(null)}
          />
        ) : (
          <Symbols onSymbolClick={handleSymbolClick} />
        )}
      </div>
    </div>
  );
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <AppContent />
        <Toaster />
      </TooltipProvider>
    </QueryClientProvider>
  );
}

export default App;
