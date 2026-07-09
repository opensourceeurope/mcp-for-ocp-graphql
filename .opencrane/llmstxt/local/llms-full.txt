# Query Fields

## `account` → `Account`

  **Args:**
  - `id: String`
  - `slug: String`
  - `githubHandle: String`
  - `throwIfMissing: Boolean`

## `accounts` → `AccountCollection!`

  **Args:**
  - `limit: Int!`
  - `offset: Int!`
  - `searchTerm: String`
  - `tag: [String]`
  - `tagSearchOperator: TagSearchOperator!`
  - `includeArchived: Boolean`
  - `skipGuests: Boolean`
  - `isActive: Boolean`
  - `skipRecentAccounts: Boolean`
  - `country: [CountryISO]`
  - `host: [AccountReferenceInput]`
  - `parent: [AccountReferenceInput]`
  - `type: [AccountType]`
  - `isHost: Boolean`
  - `onlyOpenToApplications: Boolean`
  - `hasCustomContributionsEnabled: Boolean`
  - `orderBy: OrderByInput`
  - `includeVendorsForHost: AccountReferenceInput`
  - `consolidatedBalance: AmountRangeInput`
  - `plan: [String]`
  - `isPlatformSubscriber: Boolean`
  - `isVerified: Boolean`
  - `isFirstPartyHost: Boolean`
  - `lastTransactionFrom: DateTime`
  - `lastTransactionTo: DateTime`

## `activities` → `ActivityCollection!`

  **Args:**
  - `limit: Int!`
  - `offset: Int!`
  - `individual: AccountReferenceInput`
  - `account: [AccountReferenceInput!]`
  - `host: AccountReferenceInput`
  - `includeChildrenAccounts: Boolean!`
  - `excludeParentAccount: Boolean!`
  - `includeHostedAccounts: Boolean!`
  - `dateFrom: DateTime`
  - `dateTo: DateTime`
  - `type: [ActivityAndClassesType!]`
  - `timeline: Boolean!`
  - `orderBy: ChronologicalOrderInput!`

## `application` → `Application`

  **Args:**
  - `id: String`
  - `clientId: String`

## `collective` → `Collective`

  **Args:**
  - `id: String`
  - `slug: String`
  - `githubHandle: String`
  - `throwIfMissing: Boolean`

## `conversation` → `Conversation`

  **Args:**
  - `id: String!` (required)

## `community` → `AccountCollection!`

Return accounts that have interacted with a given account or host

  **Args:**
  - `account: AccountReferenceInput`
  - `host: AccountReferenceInput!` (required)
  - `type: [AccountType]`
  - `searchTerm: String`
  - `relation: [CommunityRelationType!]`
  - `orderBy: OrderByInput`
  - `totalContributed: AmountRangeInput`
  - `totalExpended: AmountRangeInput`
  - `limit: Int!`
  - `offset: Int!`

## `currencyExchangeRate` → `[CurrencyExchangeRate!]!`

Get exchange rates from Open Collective

  **Args:**
  - `requests: [CurrencyExchangeRateRequest!]!` (required)

## `event` → `Event`

  **Args:**
  - `id: String`
  - `slug: String`
  - `githubHandle: String`
  - `throwIfMissing: Boolean`

## `expense` → `Expense`

  **Args:**
  - `expense: ExpenseReferenceInput`
  - `draftKey: String`

## `expenses` → `ExpenseCollection!`

  **Args:**
  - `limit: Int!`
  - `offset: Int!`
  - `fromAccount: AccountReferenceInput`
  - `fromAccounts: [AccountReferenceInput]`
  - `account: AccountReferenceInput`
  - `accounts: [AccountReferenceInput]`
  - `host: AccountReferenceInput`
  - `fromHost: AccountReferenceInput`
  - `hostContext: HostContext`
  - `createdByAccount: AccountReferenceInput`
  - `paidByAccount: AccountReferenceInput`
  - `approvedByAccount: AccountReferenceInput`
  - `rejectedByAccount: AccountReferenceInput`
  - `invitedByAccount: AccountReferenceInput`
  - `status: [ExpenseStatusFilter]`
  - `type: ExpenseType`
  - `types: [ExpenseType]`
  - `tag: [String]`
  - `orderBy: ChronologicalOrderInput!`
  - `amount: AmountRangeInput`
  - `minAmount: Int`
  - `maxAmount: Int`
  - `payoutMethodType: PayoutMethodType`
  - `dateFrom: DateTime`
  - `dateTo: DateTime`
  - `searchTerm: String`
  - `includeChildrenExpenses: Boolean!`
  - `customData: JSON`
  - `chargeHasReceipts: Boolean`
  - `virtualCards: [VirtualCardReferenceInput]`
  - `lastCommentBy: [LastCommentBy]`
  - `accountingCategory: [String]`
  - `payoutMethod: PayoutMethodReferenceInput`
  - `activity: ExpenseActivityFilter`
  - `kycStatus: ExpenseKYCStatusFilter`

## `expenseTagStats` → `TagStatsCollection!`

  **Args:**
  - `tagSearchTerm: String`
  - `host: AccountReferenceInput`
  - `account: AccountReferenceInput`
  - `limit: Int!`
  - `offset: Int!`

## `exportRequest` → `ExportRequest`

  **Args:**
  - `exportRequest: ExportRequestReferenceInput!` (required)
  - `throwIfMissing: Boolean!`

## `exportRequests` → `ExportRequestCollection!`

  **Args:**
  - `limit: Int!`
  - `offset: Int!`
  - `account: AccountReferenceInput!` (required)
  - `type: ExportRequestType`
  - `status: ExportRequestStatus`

## `fund` → `Fund`

  **Args:**
  - `id: String`
  - `slug: String`
  - `githubHandle: String`
  - `throwIfMissing: Boolean`

## `host` → `Host`

  **Args:**
  - `id: String`
  - `slug: String`
  - `githubHandle: String`
  - `throwIfMissing: Boolean`

## `hosts` → `HostCollection`

  **Args:**
  - `limit: Int!`
  - `offset: Int!`
  - `searchTerm: String`
  - `tag: [String]`
  - `tagSearchOperator: TagSearchOperator!`
  - `includeArchived: Boolean`
  - `skipGuests: Boolean`
  - `isActive: Boolean`
  - `skipRecentAccounts: Boolean`
  - `country: [CountryISO]`
  - `currency: String`

## `individual` → `Individual`

  **Args:**
  - `id: String`
  - `slug: String`
  - `githubHandle: String`
  - `throwIfMissing: Boolean`

## `memberInvitations` → `[MemberInvitation]`

Returns the pending invitations, or null if not allowed.

  **Args:**
  - `memberAccount: AccountReferenceInput`
  - `account: AccountReferenceInput`
  - `role: [MemberRole]`

## `order` → `Order`

  **Args:**
  - `order: OrderReferenceInput!` (required)

## `orders` → `OrderCollection!`

  **Args:**
  - `account: AccountReferenceInput`
  - `limit: Int!`
  - `offset: Int!`
  - `accountingCategory: [String]`
  - `hostContext: HostContext`
  - `includeChildrenAccounts: Boolean!`
  - `pausedBy: [OrderPausedBy]`
  - `paymentMethod: [PaymentMethodReferenceInput]`
  - `paymentMethodService: [PaymentMethodService]`
  - `paymentMethodType: [PaymentMethodType]`
  - `manualPaymentProvider: [ManualPaymentProviderReferenceInput!]`
  - `includeIncognito: Boolean`
  - `filter: AccountOrdersFilter`
  - `frequency: [ContributionFrequency]`
  - `status: [OrderStatus]`
  - `orderBy: ChronologicalOrderInput!`
  - `amount: AmountRangeInput`
  - `minAmount: Int`
  - `maxAmount: Int`
  - `dateFrom: DateTime`
  - `dateTo: DateTime`
  - `expectedDateFrom: DateTime`
  - `expectedDateTo: DateTime`
  - `chargedDateFrom: DateTime`
  - `chargedDateTo: DateTime`
  - `searchTerm: String`
  - `tier: [TierReferenceInput]`
  - `onlySubscriptions: Boolean`
  - `onlyActiveSubscriptions: Boolean`
  - `expectedFundsFilter: ExpectedFundsFilter`
  - `oppositeAccount: AccountReferenceInput`
  - `hostedAccounts: [AccountReferenceInput]`
  - `host: AccountReferenceInput`
  - `oppositeAccountScope: OppositeAccountScope`
  - `createdBy: [AccountReferenceInput]`

## `organization` → `Organization`

  **Args:**
  - `id: String`
  - `slug: String`
  - `githubHandle: String`
  - `throwIfMissing: Boolean`

## `project` → `Project`

  **Args:**
  - `id: String`
  - `slug: String`
  - `githubHandle: String`
  - `throwIfMissing: Boolean`

## `search` → `SearchResponse!`

[!] Warning: this query is currently in beta and the API might change

  **Args:**
  - `searchTerm: String!` (required)
  - `account: AccountReferenceInput`
  - `host: AccountReferenceInput`
  - `useTopHits: Boolean!`
  - `timeout: Int!`
  - `defaultLimit: Int!`

## `tagStats` → `TagStatsCollection!`

  **Args:**
  - `searchTerm: String`
  - `tagSearchTerm: String`
  - `host: AccountReferenceInput`
  - `limit: Int!`
  - `offset: Int!`

## `tier` → `Tier`

  **Args:**
  - `tier: TierReferenceInput!` (required)
  - `throwIfMissing: Boolean!`

## `transaction` → `Transaction`

Fetch a single transaction

  **Args:**
  - `transaction: TransactionReferenceInput`

## `transactions` → `TransactionCollection!`

  **Args:**
  - `account: [AccountReferenceInput!]`
  - `limit: Int!`
  - `offset: Int!`
  - `type: TransactionType`
  - `paymentMethodType: [PaymentMethodType]`
  - `paymentMethodService: [PaymentMethodService]`
  - `excludeAccount: [AccountReferenceInput]`
  - `fromAccount: AccountReferenceInput`
  - `host: AccountReferenceInput`
  - `orderBy: ChronologicalOrderInput!`
  - `amount: AmountRangeInput`
  - `dateFrom: DateTime`
  - `dateTo: DateTime`
  - `clearedFrom: DateTime`
  - `clearedTo: DateTime`
  - `searchTerm: String`
  - `hasDebt: Boolean`
  - `hasExpense: Boolean`
  - `expense: ExpenseReferenceInput`
  - `expenseType: [ExpenseType]`
  - `hasOrder: Boolean`
  - `order: OrderReferenceInput`
  - `manualPaymentProvider: [ManualPaymentProviderReferenceInput!]`
  - `includeHost: Boolean!`
  - `includeRegularTransactions: Boolean!`
  - `includeIncognitoTransactions: Boolean!`
  - `includeChildrenTransactions: Boolean!`
  - `includeGiftCardTransactions: Boolean!`
  - `includeDebts: Boolean!`
  - `includeEditedReversedTransactions: Boolean!`
  - `kind: [TransactionKind]`
  - `group: [String]`
  - `virtualCard: [VirtualCardReferenceInput]`
  - `isRefund: Boolean`
  - `merchantId: [String]`
  - `accountingCategory: [String]`
  - `paymentMethod: [PaymentMethodReferenceInput]`
  - `payoutMethod: PayoutMethodReferenceInput`

## `transactionGroups` → `TransactionGroupCollection!`

[!] Warning: this query is currently in beta and the API might change

  **Args:**
  - `account: AccountReferenceInput!` (required)
  - `limit: Int!`
  - `offset: Int!`
  - `type: TransactionType`
  - `kind: TransactionKind`
  - `dateFrom: DateTime`
  - `dateTo: DateTime`

## `transactionsImport` → `TransactionsImport`

Fetch a transactions import

  **Args:**
  - `id: NonEmptyString!` (required)

## `update` → `Update`

  **Args:**
  - `id: String`
  - `slug: String`
  - `account: AccountReferenceInput`

## `updates` → `UpdateCollection!`

This query currently returns only published updates

  **Args:**
  - `limit: Int!`
  - `offset: Int!`
  - `accountTag: [String]`
  - `accountType: [AccountType]`
  - `host: [AccountReferenceInput]`
  - `onlyChangelogUpdates: Boolean`
  - `orderBy: UpdateChronologicalOrderInput!`

## `paypalPlan` → `PaypalPlan!`

  **Args:**
  - `account: AccountReferenceInput!` (required)
  - `amount: AmountInput!` (required)
  - `frequency: ContributionFrequency!` (required)
  - `order: OrderReferenceInput`
  - `tier: TierReferenceInput`

## `personalToken` → `PersonalToken`

Get a personal token by reference

  **Args:**
  - `id: String`

## `virtualCard` → `VirtualCard`

  **Args:**
  - `virtualCard: VirtualCardReferenceInput!` (required)
  - `throwIfMissing: Boolean!`

## `virtualCardRequest` → `VirtualCardRequest`

  **Args:**
  - `virtualCardRequest: VirtualCardRequestReferenceInput!` (required)
  - `throwIfMissing: Boolean!`

## `virtualCardRequests` → `VirtualCardRequestCollection!`

  **Args:**
  - `limit: Int!`
  - `offset: Int!`
  - `host: AccountReferenceInput!` (required)
  - `status: [VirtualCardRequestStatus]`
  - `collective: [AccountReferenceInput]`

## `hostApplication` → `HostApplication`

  **Args:**
  - `hostApplication: HostApplicationReferenceInput`

## `offPlatformTransactionsInstitutions` → `[OffPlatformTransactionsInstitution!]!`

Get financial institutions for off-platform transactions

  **Args:**
  - `country: String!` (required)
  - `provider: OffPlatformTransactionsProvider!` (required)

## `loggedInAccount` → `Individual`

## `me` → `Individual`

## `paymentIntents` → `PaymentIntentCollection!`

Returns a list of payment intents

  **Args:**
  - `account: AccountReferenceInput`
  - `limit: Int!`
  - `offset: Int!`
  - `host: AccountReferenceInput`
  - `direction: PaymentIntentDirection`
  - `includeChildrenPaymentIntents: Boolean!`
  - `status: [PaymentIntentStatus!]`
  - `type: [PaymentIntentType!]`
  - `dateFrom: DateTime`
  - `dateTo: DateTime`
  - `counterparty: AccountReferenceInput`

## `platformSubscriptionTiers` → `[PlatformSubscriptionTier]`
