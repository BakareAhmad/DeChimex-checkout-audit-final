using DeChimex.Domain.Common;

namespace DeChimex.Domain.Entities;

/// <summary>
/// One message inside an <see cref="InternalConversation"/>. Unread state is per
/// recipient: the message starts unread (ReadAtUtc null) and the recipient clears it
/// by opening the conversation (MarkRead). The sender never marks their own copy.
/// </summary>
public sealed class InternalMessage : AggregateRoot
{
    public const int MaxBodyLength = 2000;

    private InternalMessage() { } // EF

    private InternalMessage(Guid conversationId, Guid senderId, string body)
    {
        ConversationId = conversationId;
        SenderId = senderId;
        Body = body;
        SentAtUtc = DateTime.UtcNow;
    }

    public Guid ConversationId { get; private set; }
    public Guid SenderId { get; private set; }
    public string Body { get; private set; } = default!;
    public DateTime SentAtUtc { get; private set; }

    /// <summary>When the recipient opened the conversation; null = unread.</summary>
    public DateTime? ReadAtUtc { get; private set; }
    public bool IsRead => ReadAtUtc is not null;

    public static InternalMessage Send(Guid conversationId, Guid senderId, string body)
    {
        var trimmed = (body ?? string.Empty).Trim();
        if (trimmed.Length == 0)
            throw new InvalidOperationException("The message is empty.");
        if (trimmed.Length > MaxBodyLength)
            throw new InvalidOperationException($"The message is longer than {MaxBodyLength} characters.");
        return new InternalMessage(conversationId, senderId, trimmed);
    }

    /// <summary>Idempotent recipient-side read mark.</summary>
    public void MarkRead()
    {
        ReadAtUtc ??= DateTime.UtcNow;
    }
}
