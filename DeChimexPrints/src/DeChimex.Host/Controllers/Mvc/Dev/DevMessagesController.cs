using DeChimex.Application.Features.InternalMessages;
using DeChimex.Contracts.InternalMessages;
using DeChimex.Domain.Entities;
using DeChimex.Shared.Constants;
using Microsoft.AspNetCore.Mvc;

namespace DeChimex.Host.Controllers.Mvc.Dev;

/// <summary>
/// The developer side of internal (work) messaging: the developer may hold one-to-one
/// conversations with the Owner and Managers only (see InternalMessaging). Lives in the
/// Developer Portal with its own layout and live permission re-checks; business roles
/// use /admin/team-messages instead. Customers can never reach either.
/// </summary>
[Route("dev/messages")]
public sealed class DevMessagesController : DevControllerBase
{
    private bool IsDeveloper => InternalMessaging.CategoryFor(CurrentUser.Roles) == InternalMessaging.Developer;

    [HttpGet]
    public async Task<IActionResult> Index()
    {
        if (!IsDeveloper) return Forbid();
        if (CurrentUser.UserId is not Guid userId) return Challenge();

        ViewData["Title"] = "Messages";
        ViewData["DevNav"] = "messages";
        ViewBag.DevPortal = true;
        ViewBag.MyUserId = userId;
        ViewBag.MyCategory = InternalMessaging.Developer;
        ViewBag.Conversations = await Sender.Send(new GetInternalConversationsQuery(userId));
        ViewBag.Contacts = await Sender.Send(new GetTeamContactsQuery(userId));
        return View("~/Views/TeamMessages/Index.cshtml");
    }

    [HttpGet("{id:guid}")]
    public async Task<IActionResult> Conversation(Guid id)
    {
        if (!IsDeveloper) return Forbid();
        if (CurrentUser.UserId is not Guid userId) return Challenge();

        await Sender.Send(new MarkInternalConversationReadCommand(userId, id));
        var detail = await Sender.Send(new GetInternalConversationQuery(userId, id));

        ViewData["Title"] = $"Conversation with {detail.OtherName}";
        ViewData["DevNav"] = "messages";
        ViewBag.DevPortal = true;
        ViewBag.MyUserId = userId;
        return View("~/Views/TeamMessages/Conversation.cshtml", detail);
    }

    [HttpPost("start")]
    [ValidateAntiForgeryToken]
    public async Task<IActionResult> Start([FromForm] Guid otherUserId)
    {
        if (!IsDeveloper) return Forbid();
        if (CurrentUser.UserId is not Guid userId) return Challenge();

        try
        {
            var conversationId = await Sender.Send(new StartInternalConversationCommand(userId, otherUserId));
            return RedirectToAction(nameof(Conversation), new { id = conversationId });
        }
        catch (DeChimex.Application.Common.Exceptions.NotFoundException)
        {
            TempData["Error"] = "You are not allowed to start a conversation with that user.";
            return RedirectToAction(nameof(Index));
        }
    }

    [HttpPost("{id:guid}/send")]
    [ValidateAntiForgeryToken]
    public async Task<IActionResult> Send(Guid id, [FromForm] string? body)
    {
        if (!IsDeveloper) return Forbid();
        if (CurrentUser.UserId is not Guid userId) return Challenge();

        var trimmed = (body ?? string.Empty).Trim();
        if (trimmed.Length == 0)
            TempData["Error"] = "Enter a message before sending.";
        else if (trimmed.Length > InternalMessage.MaxBodyLength)
            TempData["Error"] = $"Messages are limited to {InternalMessage.MaxBodyLength} characters.";
        else
        {
            try
            {
                await Sender.Send(new SendInternalMessageCommand(userId, id, trimmed));
                return RedirectToAction(nameof(Conversation), new { id });
            }
            catch (DeChimex.Application.Common.Exceptions.NotFoundException)
            {
                TempData["Error"] = "This conversation is not available.";
                return RedirectToAction(nameof(Index));
            }
            catch (DeChimex.Application.Common.Exceptions.ConflictException ex)
            {
                TempData["Error"] = ex.Message;
            }
        }
        return RedirectToAction(nameof(Conversation), new { id });
    }

    [HttpPost("{id:guid}/read")]
    [ValidateAntiForgeryToken]
    public async Task<IActionResult> MarkRead(Guid id)
    {
        if (!IsDeveloper) return Forbid();
        if (CurrentUser.UserId is not Guid userId) return Challenge();
        await Sender.Send(new MarkInternalConversationReadCommand(userId, id));
        return Json(new { ok = true });
    }

    [HttpGet("unread-count")]
    public async Task<IActionResult> UnreadCount()
    {
        if (!IsDeveloper) return Json(new { count = 0 });
        var count = CurrentUser.UserId is Guid userId
            ? await Sender.Send(new GetUnreadInternalMessageCountQuery(userId))
            : 0;
        return Json(new { count });
    }
}
