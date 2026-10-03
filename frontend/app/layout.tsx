import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
 title: "Autonomous Recovery Engine | NVIDIA Nemotron Mission Control",
 description:
  "Stateful AI-driven incident remediation powered by NVIDIA Nemotron, LangGraph, isolated Docker execution, and GitHub automation.",
 applicationName: "Autonomous Recovery Engine"
};

export default function RootLayout({
 children
}: Readonly<{
 children: React.ReactNode;
}>) {
 return (
  <html lang="en" className="dark">
   <head>
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link
     rel="preconnect"
     href="https://fonts.gstatic.com"
     crossOrigin=""
    />
    <link
     href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600;700&family=Space+Grotesk:wght@500;600;700&display=swap"
     rel="stylesheet"
    />
    <link
     href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200&display=swap"
     rel="stylesheet"
    />
   </head>
   <body className="bg-surface-container-lowest font-body-md text-on-surface antialiased selection:bg-primary-container selection:text-on-primary-container min-h-screen">
    {children}
   </body>
  </html>
 );
}
