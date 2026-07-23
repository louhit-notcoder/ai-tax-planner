import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "@/index.css";
import App from "@/App";
import ErrorBoundary from "@/components/ErrorBoundary";

const queryClient=new QueryClient({defaultOptions:{queries:{staleTime:60_000,refetchOnWindowFocus:false,retry:1}}});
const element=document.getElementById("root");if(!element)throw new Error("Root element missing");
ReactDOM.createRoot(element).render(<React.StrictMode><ErrorBoundary><QueryClientProvider client={queryClient}><App/></QueryClientProvider></ErrorBoundary></React.StrictMode>);
