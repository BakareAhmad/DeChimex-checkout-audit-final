using DeChimex.Application.Features.InternalMessages;
using DeChimex.Contracts.InternalMessages;
using DeChimex.Domain.Entities;
using DeChimex.Shared.Constants;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;

namespace DeChimex.Host.Controllers.Mvc.Admin;

/// <summary>
/// Internal (work) messaging for the business roles: Owner, Manager and Staff.
/// The pairing rules (who may talk to whom) are enforced server-side here AND in the
/// application layer; developers use their own portal side (/dev/messages) and
/// customers never pass the [Authorize] + category guard. Kept fully separate from
/// customer/order conversations (/admin/messages).
/// </summary>
[Authorize]
[Route("admin/team-messages")]
public sealed class AdminTeamMessagesController : MvcControllerBase
{
    private string? Category => InternalMessaging.CategoryFor(CurrentUser.Roles);
    private bool IsBusinessRole => Category is InternalMessaging.Owner or InternalMessaging.Manager or InternalMessaging.Staff;

    [HttpGet]
    public async Task<IActionResult> Index()
    {
        if (!IsBusinessRole) return Forbid();
        if (CurrentUser.UserId is not Guid userId) return Challenge();

        ViewData["Title"] = "Team messages";
        ViewData["Heading"] = "Team messages";
        ViewData["ActiveNav"] = "team-messages";
        ViewBag.DevPortal = false;
        ViewBag.MyUserId = userId;
        ViewBag.MyCategory = Category;
        ViewBag.Conversations = await Sender.Send(new GetInternalConversationsQuery(userId));
        ViewBag.Contacts = await Sender.Send(new GetTeamContactsQuery(userId));
        return View("~/Views/TeamMessages/Index.cshtml");
    }

    [HttpGet("{id:guid}")]
    public async Task<IActionResult> Conversation(Guid id)
    {
        if (!IsBusinessRole) return Forbid();
        if (CurrentUser.UserId is not Guid userId) return Challenge();

        // Opening the conversation clears the recipient's unread state, then the
        // detail is loaded so the rendered page already shows everything as read.
        await Sender.Send(new MarkInternalConversationReadCommand(userId, id));
        var detail = await Sender.Send(new GetInternalConversationQuery(userId, id));

        ViewData["Title"] = $"Conversation with {detail.OtherName}";
        ViewData["Heading"] = "Team messages";
        ViewData["ActiveNav"] = "team-messages";
        ViewBag.DevPortal = false;
        ViewBag.MyUserId = userId;
        return View("~/Views/TeamMessages/Conversation.cshtml", detail);
    }

    [HttpPost("start")]
    [ValidateAntiForgeryToken]
    public async Task<IActionResult> Start([FromForm] Guid otherUserId)
    {
        if (!IsBusinessRole) return Forbid();
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
        if (!IsBusinessRole) return Forbid();
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

    /// <summary>JS companion: clears unread state when the recipient has the page open.</summary>
    [HttpPost("{id:guid}/read")]
    [ValidateAntiForgeryToken]
    public async Task<IActionResult> MarkRead(Guid id)
    {
        if (!IsBusinessRole) return Forbid();
        if (CurrentUser.UserId is not Guid userId) return Challenge();
        await Sender.Send(new MarkInternalConversationReadCommand(userId, id));
        return Json(new { ok = true });
    }

    /// <summary>Sidebar badge count for the current business user.</summary>
    [HttpGet("unread-count")]
    public async Task<IActionResult> UnreadCount()
    {
        if (!IsBusinessRole) return Json(new { count = 0 });
        var count = CurrentUser.UserId is Guid userId
            ? await Sender.Send(new GetUnreadInternalMessageCountQuery(userId))
            : 0;
        return Json(new { count });
    }
}
