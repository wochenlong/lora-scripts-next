import type { AppLocale } from "../index"
import enUS from "./en-US"
import zhTW from "./zh-TW"
import zhHK from "./zh-HK"
import jaJP from "./ja-JP"
import koKR from "./ko-KR"

export const schemaDescMessages: Partial<Record<AppLocale, Record<string, string>>> = {
  "en-US": enUS,
  "zh-TW": zhTW,
  "zh-HK": zhHK,
  "ja-JP": jaJP,
  "ko-KR": koKR,
}
