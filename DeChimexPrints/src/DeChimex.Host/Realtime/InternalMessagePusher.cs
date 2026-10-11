using DeChimex.Application.Common.Interfaces;
using Microsoft.AspNetCore.SignalR;

namespace DeChimex.Host.Realtime;

/// <summary>Wire-format payload sent to the recipient on the "internalMessage" event.
/// Lets an open conversation render the message live and the sidebar badge update
/// without a reload.</summary>
public sealed record InternalMessagePushDto(
    Guid ConversationId,
    Guid MessageId,
    Guid SenderId,
    string SenderName,
    string Body,
    DateTime SentUtc);

/// <summary>Delivers a live internal (work) message to the recipient's browser through
/// the notification hub's per-user group (every authenticated account joins it, so the
/// developer portal receives these too). Registered as singleton: IHubContext is
/// application-scoped.</summary>
public sealed class InternalMessagePusher(IHubContext<NotificationHub> hub) : IInternalMessagePusher
{
    public const string EventName = "internalMessage";

    public Task PushAsync(Guid recipientUserId, Guid conversationId, Guid messageId, Guid senderId,
        string senderName, string body, DateTime sentUtc, CancellationToken ct = default)
    {
        var payload = new InternalMessagePushDto(conversationId, messageId, senderId, senderName, body, sentUtc);
        return hub.Clients.Group(NotificationHub.UserGroup(recipientUserId)).SendAsync(EventName, payload, ct);
    }
}
