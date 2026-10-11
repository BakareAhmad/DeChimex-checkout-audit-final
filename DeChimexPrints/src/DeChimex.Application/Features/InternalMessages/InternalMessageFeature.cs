using DeChimex.Application.Common.Exceptions;
using DeChimex.Application.Common.Interfaces;
using DeChimex.Application.Common.Messaging;
using DeChimex.Contracts.InternalMessages;
using DeChimex.Domain.Entities;
using DeChimex.Domain.Enums;
using DeChimex.Domain.Repositories;
using DeChimex.Shared.Constants;
using MediatR;

namespace DeChimex.Application.Features.InternalMessages;

/// <summary>
/// Internal (work) one-to-one messaging between authorized roles (owner directive
/// 2026-10-07). Every handler re-derives BOTH participants' communication category
/// from the database and rejects anything outside the InternalMessaging pair rules
/// with NotFoundException, so disallowed users can neither list, open, create nor
/// write conversations they are not permitted to have. Completely separate from
/// customer/order conversations.
/// </summary>
public sealed record GetTeamContactsQuery(Guid UserId) : IQuery<IReadOnlyList<TeamContactDto>>;

public sealed class GetTeamContactsHandler(IInternalMessageQueries queries)
    : IQueryHandler<GetTeamContactsQuery, IReadOnlyList<TeamContactDto>>
{
    public async Task<IReadOnlyList<TeamContactDto>> Handle(GetTeamContactsQuery q, CancellationToken ct)
    {
        var me = await queries.GetIdentityAsync(q.UserId, ct);
        if (me is null) return Array.Empty<TeamContactDto>();
        return await queries.GetContactsAsync(me.Value.UserId, me.Value.Category, ct);
    }
}

public sealed record GetInternalConversationsQuery(Guid UserId) : IQuery<IReadOnlyList<ConversationSummaryDto>>;

public sealed class GetInternalConversationsHandler(IInternalMessageQueries queries)
    : IQueryHandler<GetInternalConversationsQuery, IReadOnlyList<ConversationSummaryDto>>
{
    public async Task<IReadOnlyList<ConversationSummaryDto>> Handle(GetInternalConversationsQuery q, CancellationToken ct)
    {
        var me = await queries.GetIdentityAsync(q.UserId, ct);
        if (me is null) return Array.Empty<ConversationSummaryDto>();
        return await queries.GetConversationsAsync(q.UserId, ct);
    }
}

public sealed record GetInternalConversationQuery(Guid UserId, Guid ConversationId) : IQuery<ConversationDetailDto>;

public sealed class GetInternalConversationHandler(IInternalMessageQueries queries)
    : IQueryHandler<GetInternalConversationQuery, ConversationDetailDto>
{
    public async Task<ConversationDetailDto> Handle(GetInternalConversationQuery q, CancellationToken ct)
    {
        var me = await queries.GetIdentityAsync(q.UserId, ct)
            ?? throw new NotFoundException("Conversation", q.ConversationId);
        return await queries.GetConversationAsync(me.UserId, q.ConversationId, ct)
            ?? throw new NotFoundException("Conversation", q.ConversationId);
    }
}

public sealed record GetUnreadInternalMessageCountQuery(Guid UserId) : IQuery<int>;

public sealed class GetUnreadInternalMessageCountHandler(IInternalMessageQueries queries)
    : IQueryHandler<GetUnreadInternalMessageCountQuery, int>
{
    public async Task<int> Handle(GetUnreadInternalMessageCountQuery q, CancellationToken ct)
    {
        var me = await queries.GetIdentityAsync(q.UserId, ct);
        if (me is null) return 0;
        return await queries.CountUnreadAsync(q.UserId, ct);
    }
}

/// <summary>Gets or creates the caller's conversation with another user. The pairing
/// rule check runs against fresh DB categories; a denied pair reads as "user not
/// found" so staff cannot probe who is reachable.</summary>
public sealed record StartInternalConversationCommand(Guid ActorId, Guid OtherUserId) : ICommand<Guid>;

public sealed class StartInternalConversationHandler(
    IInternalConversationRepository conversations, IInternalMessageQueries queries, IUnitOfWork uow)
    : ICommandHandler<StartInternalConversationCommand, Guid>
{
    public async Task<Guid> Handle(StartInternalConversationCommand c, CancellationToken ct)
    {
        if (c.ActorId == c.OtherUserId)
            throw new NotFoundException("User", c.OtherUserId);

        var me = await queries.GetIdentityAsync(c.ActorId, ct)
            ?? throw new NotFoundException("User", c.OtherUserId);
        var other = await queries.GetIdentityAsync(c.OtherUserId, ct)
            ?? throw new NotFoundException("User", c.OtherUserId);

        if (!InternalMessaging.CanCommunicate(me.Category, other.Category))
            throw new NotFoundException("User", c.OtherUserId);

        var existing = await conversations.FindBetweenAsync(me.UserId, other.UserId, ct);
        if (existing is not null) return existing.Id;

        var conversation = InternalConversation.Start(me.UserId, other.UserId);
        await conversations.AddAsync(conversation, ct);
        await uow.SaveChangesAsync(ct);
        return conversation.Id;
    }
}

/// <summary>Sends one message into an existing conversation the actor participates in,
/// raises the recipient's in-app notification and pushes the live "internalMessage"
/// event (best effort).</summary>
public sealed record SendInternalMessageCommand(Guid ActorId, Guid ConversationId, string Body) : ICommand<Guid>;

public sealed class SendInternalMessageHandler(
    IInternalConversationRepository conversations, IInternalMessageRepository messages,
    IInternalMessageQueries queries, IUnitOfWork uow,
    INotificationService notifications, IInternalMessagePusher pusher)
    : ICommandHandler<SendInternalMessageCommand, Guid>
{
    public async Task<Guid> Handle(SendInternalMessageCommand c, CancellationToken ct)
    {
        var body = (c.Body ?? string.Empty).Trim();
        if (body.Length == 0 || body.Length > InternalMessage.MaxBodyLength)
            throw new ConflictException("message.invalid", "Enter a message between 1 and 2000 characters.");

        var me = await queries.GetIdentityAsync(c.ActorId, ct)
            ?? throw new NotFoundException("Conversation", c.ConversationId);

        var conversation = await conversations.GetByIdAsync(c.ConversationId, ct)
            ?? throw new NotFoundException("Conversation", c.ConversationId);
        if (!conversation.Includes(me.UserId))
            throw new NotFoundException("Conversation", c.ConversationId);

        var other = await queries.GetIdentityAsync(conversation.OtherThan(me.UserId), ct)
            ?? throw new NotFoundException("Conversation", c.ConversationId);
        if (!InternalMessaging.CanCommunicate(me.Category, other.Category))
            throw new NotFoundException("Conversation", c.ConversationId);

        var message = InternalMessage.Send(conversation.Id, me.UserId, body);
        await messages.AddAsync(message, ct);
        await uow.SaveChangesAsync(ct);

        // In-app notification for the recipient; the link lands on THEIR side of the
        // feature (dev portal for the developer, admin area for business roles).
        var preview = body.Length <= 140 ? body : body[..140] + "…";
        var link = other.Category == InternalMessaging.Developer
            ? $"/dev/messages/{conversation.Id}"
            : $"/admin/team-messages/{conversation.Id}";
        await notifications.NotifyAsync(NotificationType.NewMessage,
            $"Internal message from {me.Name}", preview, other.UserId, link, null, ct);

        // Live delivery is best effort: a failed push never rolls back the message.
        try
        {
            await pusher.PushAsync(other.UserId, conversation.Id, message.Id, me.UserId, me.Name, message.Body, message.SentAtUtc, ct);
        }
        catch
        {
            // Swallowed by design (same contract as the notification pusher).
        }

        return message.Id;
    }
}

/// <summary>Recipient opens a conversation: every message from the other participant
/// becomes read (idempotent). Participants-only, enforced like every other command.</summary>
public sealed record MarkInternalConversationReadCommand(Guid UserId, Guid ConversationId) : ICommand<Unit>;

public sealed class MarkInternalConversationReadHandler(
    IInternalConversationRepository conversations, IInternalMessageRepository messages, IUnitOfWork uow)
    : ICommandHandler<MarkInternalConversationReadCommand, Unit>
{
    public async Task<Unit> Handle(MarkInternalConversationReadCommand c, CancellationToken ct)
    {
        var conversation = await conversations.GetByIdAsync(c.ConversationId, ct)
            ?? throw new NotFoundException("Conversation", c.ConversationId);
        if (!conversation.Includes(c.UserId))
            throw new NotFoundException("Conversation", c.ConversationId);

        var unread = await messages.GetUnreadFromAsync(conversation.Id, conversation.OtherThan(c.UserId), ct);
        if (unread.Count == 0) return Unit.Value;

        foreach (var message in unread)
        {
            message.MarkRead();
            messages.Update(message);
        }
        await uow.SaveChangesAsync(ct);
        return Unit.Value;
    }
}
