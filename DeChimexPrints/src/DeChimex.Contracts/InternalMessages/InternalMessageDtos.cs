namespace DeChimex.Contracts.InternalMessages;

/// <summary>A user the caller is allowed to start an internal conversation with
/// (role-pair rules already applied — disallowed users are never listed).</summary>
public sealed record TeamContactDto(Guid UserId, string Name, string Category, string RoleLabel);

/// <summary>One row of the conversation inbox.</summary>
public sealed record ConversationSummaryDto(
    Guid ConversationId,
    Guid OtherUserId,
    string OtherName,
    string OtherCategory,
    string OtherRoleLabel,
    string? LastMessageBody,
    Guid? LastSenderId,
    DateTime? LastSentUtc,
    int UnreadCount);

/// <summary>A single message inside a conversation, rendered from the caller's side.</summary>
public sealed record InternalMessageDto(
    Guid Id,
    Guid SenderId,
    string SenderName,
    string Body,
    DateTime SentAtUtc,
    bool IsMine);

/// <summary>The full conversation view for one participant.</summary>
public sealed record ConversationDetailDto(
    Guid ConversationId,
    Guid OtherUserId,
    string OtherName,
    string OtherCategory,
    string OtherRoleLabel,
    IReadOnlyList<InternalMessageDto> Messages);
