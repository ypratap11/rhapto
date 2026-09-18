import type { paths } from "./schema";

type Json200<T> = T extends { responses: { 200: { content: { "application/json": infer R } } } } ? R : never;
type JsonBody<T> = T extends { requestBody: { content: { "application/json": infer R } } } ? R : never;

export type SearchBody = JsonBody<paths["/api/v1/search"]["post"]>;
export type SearchResult = Json200<paths["/api/v1/search"]["post"]>;
export type PerSource = SearchResult["per_source"];
export type SearchOut = Json200<paths["/api/v1/searches"]["get"]>[number];
export type SearchIn = JsonBody<paths["/api/v1/searches"]["post"]>;
export type DashboardOut = Json200<paths["/api/v1/dashboard"]["get"]>;
export type DashboardChecklist = DashboardOut["checklist"];
export type DueFollowup = DashboardOut["due_followups"][number];
export type DashboardSavedSearch = DashboardOut["saved_searches"][number];
export type TaxonomyOut = Json200<paths["/api/v1/taxonomy"]["get"]>;
export type TaxonomyField = TaxonomyOut["fields"][number];
export type TaxonomyRole = TaxonomyField["roles"][number];
export type TaxonomySuggestions = Json200<paths["/api/v1/taxonomy/suggestions"]["get"]>;
export type SourceSetting = Json200<paths["/api/v1/settings/sources"]["get"]>[number];
export type SourceSettingIn = JsonBody<paths["/api/v1/settings/sources/{source}"]["put"]>;
export type SourceTestOut = Json200<paths["/api/v1/settings/sources/{source}/test"]["post"]>;
