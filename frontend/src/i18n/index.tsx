import React, { createContext, useContext, useState } from "react";
import { en } from "./en";
import { th } from "./th";
import { Locale, Translations } from "./types";

const LOCALE_STORAGE_KEY = "adms.locale";

interface LanguageContextValue {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: Translations;
}

const translationsMap: Record<Locale, Translations> = {
  th,
  en,
};

const LanguageContext = createContext<LanguageContextValue>({
  locale: "th",
  setLocale: () => {},
  t: th,
});

export const LanguageProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [locale, setLocaleState] = useState<Locale>(() => {
    try {
      const stored = localStorage.getItem(LOCALE_STORAGE_KEY);
      if (stored === "en" || stored === "th") {
        return stored;
      }
    } catch {
      // localStorage may not be accessible
    }
    return "th"; // Thai default as per requirement
  });

  const setLocale = (newLocale: Locale) => {
    setLocaleState(newLocale);
    try {
      localStorage.setItem(LOCALE_STORAGE_KEY, newLocale);
    } catch {
      // ignore storage errors
    }
  };

  const t = translationsMap[locale] || th;

  return (
    <LanguageContext.Provider value={{ locale, setLocale, t }}>
      {children}
    </LanguageContext.Provider>
  );
};

export const useTranslation = () => {
  const context = useContext(LanguageContext);
  if (!context) {
    throw new Error("useTranslation must be used within a LanguageProvider");
  }
  return context;
};
