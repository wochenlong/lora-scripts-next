import type { AppLocale } from "../index"
import enUS from "./en-US"
import zhTW from "./zh-TW"
import zhHK from "./zh-HK"
import jaJP from "./ja-JP"
import koKR from "./ko-KR"
import esES from "./es-ES"
import frFR from "./fr-FR"
import deDE from "./de-DE"
import ruRU from "./ru-RU"

export const schemaDescMessages: Partial<Record<AppLocale, Record<string, string>>> = {
  "en-US": enUS,
  "zh-TW": zhTW,
  "zh-HK": zhHK,
  "ja-JP": jaJP,
  "ko-KR": koKR,
  "es-ES": esES,
  "fr-FR": frFR,
  "de-DE": deDE,
  "ru-RU": ruRU,
}
