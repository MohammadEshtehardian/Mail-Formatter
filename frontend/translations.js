// Translation strings for English and Persian
const translations = {
    en: {
        appTitle: "📧 Mail Formatter",
        subtitle: "AI-powered email improvement with real-time progress tracking",
        improveEmail: "Improve Your Email",
        subject: "Subject",
        emailBody: "Email Body",
        subjectPlaceholder: "Enter email subject...",
        bodyPlaceholder: "Enter your email content here...",
        improveEmailBtn: "Improve Email",
        processingProgress: "Processing Progress",
        improvedEmail: "Improved Email",
        email: "Email",
        suggestions: "Suggestions",
        differences: "Differences",
        copyEmail: "Copy Email",
        copied: "✓ Copied!",
        tryAgain: "Try Again",
        error: "Error",
        poweredBy: "Powered by CrewAI Multi-Agent System",
        waiting: "Waiting...",
        processing: "Processing...",
        completed: "Completed",
        language: "Language",
        tone: "Tone",
        translation: "Translation",
        audience: "Audience",
        noTranslation: "No Translation",
        englishToPersian: "English → Persian",
        persianToEnglish: "Persian → English",
        thinking: "Thinking",
        showThinking: "Show Thinking",
        hideThinking: "Hide Thinking",
        formal: "Formal",
        professional: "Professional",
        casual: "Casual",
        friendly: "Friendly",
        polite: "Polite",
        concise: "Concise",
        general: "General",
        academic: "Academic",
        business: "Business",
        technical: "Technical",
        english: "English",
        persian: "Persian",
        emailPlanner: "Email Strategy Planner",
        toneSpecialist: "Tone and Style Specialist",
        grammarSpecialist: "Grammar and Syntax Expert",
        dictationSpecialist: "Spelling and Word Choice Specialist",
        responseFormatter: "Response Formatter and Analysis Specialist",
    },
    fa: {
        appTitle: "📧 بهبود دهنده ایمیل",
        subtitle: "بهبود ایمیل با هوش مصنوعی با ردیابی پیشرفت در زمان واقعی",
        improveEmail: "ایمیل خود را بهبود دهید",
        subject: "موضوع",
        emailBody: "متن ایمیل",
        subjectPlaceholder: "موضوع ایمیل را وارد کنید...",
        bodyPlaceholder: "محتوای ایمیل خود را اینجا وارد کنید...",
        improveEmailBtn: "بهبود ایمیل",
        processingProgress: "پیشرفت پردازش",
        improvedEmail: "ایمیل بهبود یافته",
        email: "ایمیل",
        suggestions: "پیشنهادات",
        differences: "تفاوت‌ها",
        copyEmail: "کپی ایمیل",
        copied: "✓ کپی شد!",
        tryAgain: "دوباره تلاش کنید",
        error: "خطا",
        poweredBy: "قدرت گرفته از سیستم چند عاملی CrewAI",
        waiting: "در انتظار...",
        processing: "در حال پردازش...",
        completed: "تکمیل شد",
        language: "زبان",
        tone: "تن صدا",
        translation: "ترجمه",
        audience: "مخاطب",
        noTranslation: "بدون ترجمه",
        englishToPersian: "فارسی → انگلیسی",
        persianToEnglish: "انگلیسی → فارسی",
        thinking: "تفکر",
        showThinking: "نمایش تفکر",
        hideThinking: "پنهان کردن تفکر",
        formal: "رسمی",
        professional: "حرفه‌ای",
        casual: "غیررسمی",
        friendly: "دوستانه",
        polite: "مؤدب",
        concise: "مختصر",
        general: "عمومی",
        academic: "آکادمیک",
        business: "تجاری",
        technical: "فنی",
        english: "انگلیسی",
        persian: "فارسی",
        emailPlanner: "برنامه‌ریز استراتژی ایمیل",
        toneSpecialist: "متخصص لحن و سبک",
        grammarSpecialist: "متخصص دستور زبان و نحو",
        dictationSpecialist: "متخصص املاء و انتخاب کلمه",
        responseFormatter: "متخصص فرمت‌بندی و تحلیل پاسخ",
    }
};

// Current language
let currentLang = localStorage.getItem('language') || 'en';

// Translation function
function t(key) {
    return translations[currentLang][key] || translations.en[key] || key;
}

// Set language
function setLanguage(lang) {
    currentLang = lang;
    localStorage.setItem('language', lang);
    document.documentElement.lang = lang;
    document.documentElement.dir = lang === 'fa' ? 'rtl' : 'ltr';
    updateUI();
}

// Update all UI elements with translations
function updateUI() {
    // Update all elements with data-i18n attribute
    document.querySelectorAll('[data-i18n]').forEach(el => {
        const key = el.getAttribute('data-i18n');
        if (el.tagName === 'OPTION') {
            // Options need special handling
            const optionValue = el.getAttribute('value');
            if (optionValue) {
                el.textContent = t(key);
            } else {
                el.textContent = t(key);
            }
        } else {
            el.textContent = t(key);
        }
    });
    
    // Update placeholders
    document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
        const key = el.getAttribute('data-i18n-placeholder');
        el.placeholder = t(key);
    });
    
    // Update title
    document.title = t('appTitle') + ' - AI Email Improvement';
}

// Initialize on page load
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        setLanguage(currentLang);
    });
} else {
    setLanguage(currentLang);
}
