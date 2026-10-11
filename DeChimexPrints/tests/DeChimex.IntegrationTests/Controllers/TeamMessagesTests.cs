using System.Net;
using System.Text.Json;
using Microsoft.Extensions.DependencyInjection;
using DeChimex.Shared.Constants;
using FluentAssertions;
using Microsoft.AspNetCore.Mvc.Testing;
using Xunit;

namespace DeChimex.IntegrationTests.Controllers;

/// <summary>
/// Internal (work) messaging (owner directive 2026-10-07): one-to-one conversations
/// between authorized roles only — Owner/Manager/Staff/Developer per the pair matrix,
/// staff-to-staff and staff-to-developer denied server-side, customers excluded, the
/// developer served by the portal side, unread counts raised and cleared, and the
/// recipient notified. Kept separate from customer/order conversations.
/// </summary>
public class TeamMessagesTests
{
    private const string Password = "TeamMsg!2026x";

    private static HttpClient Browser(CustomWebApplicationFactory factory) =>
        factory.CreateClient(new WebApplicationFactoryClientOptions
        {
            AllowAutoRedirect = false,
            HandleCookies = true
        });

    private static async Task<HttpClient> LoginAsync(CustomWebApplicationFactory factory, string email)
    {
        var client = Browser(factory);
        (await TestSeed.LoginMvcAsync(client, email, Password)).Should().BeTrue($"{email} should sign in");
        return client;
    }

    private static async Task<HttpResponseMessage> PostFormAsync(
        HttpClient client, string tokenPageUrl, string postUrl, Dictionary<string, string> fields)
    {
        var page = await client.GetAsync(tokenPageUrl);
        var html = await page.Content.ReadAsStringAsync();
        fields["__RequestVerificationToken"] = TestSeed.ExtractAntiforgeryToken(html);
        return await client.PostAsync(postUrl, new FormUrlEncodedContent(fields));
    }

    private static async Task<int> UnreadCountAsync(HttpClient client, string base_)
    {
        var response = await client.GetAsync($"{base_}/unread-count");
        response.StatusCode.Should().Be(HttpStatusCode.OK);
        using var doc = JsonDocument.Parse(await response.Content.ReadAsStringAsync());
        return doc.RootElement.GetProperty("count").GetInt32();
    }

    private sealed record Team(
        CustomWebApplicationFactory Factory, HttpClient Owner, HttpClient Manager,
        HttpClient Staff, HttpClient Staff2, HttpClient Dev, HttpClient Customer);

    private static async Task<Team> SeedTeamAsync()
    {
        var factory = new CustomWebApplicationFactory();
        await TestSeed.CreateStaffUserAsync(factory.Services, "manager@team.test", Password, RoleNames.Manager, "Mary", "Manager");
        await TestSeed.CreateStaffUserAsync(factory.Services, "sam@team.test", Password, RoleNames.SalesStaff, "Sam", "Staff");
        await TestSeed.CreateStaffUserAsync(factory.Services, "sue@team.test", Password, RoleNames.SalesStaff, "Sue", "Staff");
        await TestSeed.CreateStaffUserAsync(factory.Services, "dev@team.test", Password, RoleNames.Developer, "Dee", "Dev");
        await TestSeed.RegisterCustomerAsync(factory.Services, "cust@team.test", Password);
        await TestSeed.VerifyCustomerAsync(factory.Services, "cust@team.test");

        var owner = await TestSeed.LoginOwnerMvcAsync(factory.Services, () => Browser(factory));
        var manager = await LoginAsync(factory, "manager@team.test");
        var staff = await LoginAsync(factory, "sam@team.test");
        var staff2 = await LoginAsync(factory, "sue@team.test");
        var dev = await LoginAsync(factory, "dev@team.test");
        var customer = await LoginAsync(factory, "cust@team.test");
        return new Team(factory, owner, manager, staff, staff2, dev, customer);
    }

    private static async Task<Guid> UserIdOf(CustomWebApplicationFactory factory, string email)
    {
        using var scope = factory.Services.CreateScope();
        var users = scope.ServiceProvider.GetRequiredService<DeChimex.Domain.Repositories.IUserRepository>();
        var user = await users.GetByEmailAsync(email);
        user.Should().NotBeNull();
        return user!.Id;
    }

    [Fact]
    public async Task Contact_lists_follow_the_matrix_and_never_offer_disallowed_users()
    {
        var team = await SeedTeamAsync();
        using var factory = team.Factory;
        var owner = team.Owner;
        var manager = team.Manager;
        var staff = team.Staff;
        var dev = team.Dev;
        var customer = team.Customer;

        // Owner sees management, staff and the developer.
        var ownerHtml = await (await owner.GetAsync("/admin/team-messages")).Content.ReadAsStringAsync();
        ownerHtml.Should().Contain("Mary Manager").And.Contain("Sam Staff").And.Contain("Dee Dev");

        // Staff sees only management: no colleagues, no developer.
        var staffHtml = await (await staff.GetAsync("/admin/team-messages")).Content.ReadAsStringAsync();
        staffHtml.Should().Contain("Mary Manager");
        staffHtml.Should().NotContain("Sue Staff", "staff-to-staff conversations are not allowed");
        staffHtml.Should().NotContain("Dee Dev", "staff-to-developer conversations are not allowed");

        // Developer sees only management, on the portal side.
        var devHtml = await (await dev.GetAsync("/dev/messages")).Content.ReadAsStringAsync();
        devHtml.Should().Contain("Mary Manager");
        devHtml.Should().NotContain("Sam Staff").And.NotContain("Sue Staff");

        // Customer has no access at all.
        var customerResponse = await customer.GetAsync("/admin/team-messages");
        customerResponse.StatusCode.Should().BeOneOf(HttpStatusCode.Forbidden, HttpStatusCode.Redirect);
    }

    [Fact]
    public async Task Staff_cannot_start_staff_or_developer_conversations_or_read_others()
    {
        var team = await SeedTeamAsync();
        using var factory = team.Factory;
        var owner = team.Owner;
        var manager = team.Manager;
        var staff = team.Staff;
        var dev = team.Dev;
        var customer = team.Customer;
        var sueId = await UserIdOf(factory, "sue@team.test");
        var devId = await UserIdOf(factory, "dev@team.test");

        // Staff -> staff denied (reads as a plain redirect back, nothing created).
        var deniedStaff = await PostFormAsync(staff, "/admin/team-messages", "/admin/team-messages/start",
            new Dictionary<string, string> { ["otherUserId"] = sueId.ToString() });
        deniedStaff.StatusCode.Should().Be(HttpStatusCode.Redirect);
        deniedStaff.Headers.Location!.ToString().Should().Be("/admin/team-messages");

        // Staff -> developer denied the same way.
        var deniedDev = await PostFormAsync(staff, "/admin/team-messages", "/admin/team-messages/start",
            new Dictionary<string, string> { ["otherUserId"] = devId.ToString() });
        deniedDev.Headers.Location!.ToString().Should().Be("/admin/team-messages");

        var staffHtml = await (await staff.GetAsync("/admin/team-messages")).Content.ReadAsStringAsync();
        staffHtml.Should().NotContain("Sue Staff").And.NotContain("Dee Dev", "no conversation may exist for a denied pair");

        // Owner<->Manager conversation is invisible to staff (no discovery).
        var start = await PostFormAsync(owner, "/admin/team-messages", "/admin/team-messages/start",
            new Dictionary<string, string> { ["otherUserId"] = (await UserIdOf(factory, "manager@team.test")).ToString() });
        var conversationUrl = start.Headers.Location!.ToString();
        var staffPeek = await staff.GetAsync(conversationUrl);
        staffPeek.StatusCode.Should().Be(HttpStatusCode.NotFound);
    }

    [Fact]
    public async Task Owner_manager_flow_raises_unread_counts_notification_and_clears_on_open()
    {
        var team = await SeedTeamAsync();
        using var factory = team.Factory;
        var owner = team.Owner;
        var manager = team.Manager;
        var staff = team.Staff;
        var dev = team.Dev;
        var customer = team.Customer;
        var managerId = await UserIdOf(factory, "manager@team.test");

        var start = await PostFormAsync(owner, "/admin/team-messages", "/admin/team-messages/start",
            new Dictionary<string, string> { ["otherUserId"] = managerId.ToString() });
        start.StatusCode.Should().Be(HttpStatusCode.Redirect);
        var conversationUrl = start.Headers.Location!.ToString();
        conversationUrl.Should().StartWith("/admin/team-messages/");

        (await UnreadCountAsync(manager, "/admin/team-messages")).Should().Be(0);

        var send = await PostFormAsync(owner, conversationUrl, conversationUrl + "/send",
            new Dictionary<string, string> { ["body"] = "Mary, are the weekly reports ready?" });
        send.StatusCode.Should().Be(HttpStatusCode.Redirect);

        (await UnreadCountAsync(manager, "/admin/team-messages")).Should().Be(1, "the recipient has one unread message");

        // The in-app notification exists for the recipient and links to the conversation.
        var notifications = await (await manager.GetAsync("/admin/notifications")).Content.ReadAsStringAsync();
        notifications.Should().Contain("Internal message from").And.Contain(conversationUrl);

        // Inbox preview shows the message; opening the conversation clears the unread state.
        var inbox = await (await manager.GetAsync("/admin/team-messages")).Content.ReadAsStringAsync();
        inbox.Should().Contain("Mary, are the weekly reports ready?");
        var page = await (await manager.GetAsync(conversationUrl)).Content.ReadAsStringAsync();
        page.Should().Contain("Mary, are the weekly reports ready?").And.Contain("Owner", "the sender is clearly shown");
        (await UnreadCountAsync(manager, "/admin/team-messages")).Should().Be(0, "opening the conversation clears unread");
    }

    [Fact]
    public async Task Developer_uses_the_portal_side_and_roles_cannot_cross_sides()
    {
        var team = await SeedTeamAsync();
        using var factory = team.Factory;
        var owner = team.Owner;
        var manager = team.Manager;
        var staff = team.Staff;
        var dev = team.Dev;
        var customer = team.Customer;
        var managerId = await UserIdOf(factory, "manager@team.test");

        // Developer starts a conversation with the manager from the portal.
        var start = await PostFormAsync(dev, "/dev/messages", "/dev/messages/start",
            new Dictionary<string, string> { ["otherUserId"] = managerId.ToString() });
        var conversationUrl = start.Headers.Location!.ToString();
        conversationUrl.Should().StartWith("/dev/messages/");

        var send = await PostFormAsync(dev, conversationUrl, conversationUrl + "/send",
            new Dictionary<string, string> { ["body"] = "Deployment window confirmed for tonight." });
        send.StatusCode.Should().Be(HttpStatusCode.Redirect);

        // Manager sees it on the admin side with the developer's name, and the
        // notification link points at the ADMIN side for the manager.
        (await UnreadCountAsync(manager, "/admin/team-messages")).Should().Be(1);
        var inbox = await (await manager.GetAsync("/admin/team-messages")).Content.ReadAsStringAsync();
        inbox.Should().Contain("Dee Dev").And.Contain("Deployment window confirmed for tonight.");

        // Side separation: developer cannot use the admin area, staff cannot use the dev portal.
        (await dev.GetAsync("/admin/team-messages")).StatusCode
            .Should().BeOneOf(HttpStatusCode.Forbidden, HttpStatusCode.Redirect, HttpStatusCode.NotFound);
        (await staff.GetAsync("/dev/messages")).StatusCode
            .Should().BeOneOf(HttpStatusCode.Forbidden, HttpStatusCode.Redirect, HttpStatusCode.NotFound);

        // Developer unread badge endpoint lives on the portal side.
        (await UnreadCountAsync(dev, "/dev/messages")).Should().Be(0, "the sender has no unread messages");
    }

    [Fact]
    public async Task Message_body_validation_rejects_empty_and_overlong_bodies()
    {
        var team = await SeedTeamAsync();
        using var factory = team.Factory;
        var owner = team.Owner;
        var manager = team.Manager;
        var staff = team.Staff;
        var dev = team.Dev;
        var customer = team.Customer;
        var managerId = await UserIdOf(factory, "manager@team.test");
        var start = await PostFormAsync(owner, "/admin/team-messages", "/admin/team-messages/start",
            new Dictionary<string, string> { ["otherUserId"] = managerId.ToString() });
        var conversationUrl = start.Headers.Location!.ToString();

        // Empty body: redirected back, nothing persisted.
        await PostFormAsync(owner, conversationUrl, conversationUrl + "/send",
            new Dictionary<string, string> { ["body"] = "   " });
        // Overlong body (2001 chars): redirected back, nothing persisted.
        await PostFormAsync(owner, conversationUrl, conversationUrl + "/send",
            new Dictionary<string, string> { ["body"] = new string('b', 2001) });

        var page = await (await owner.GetAsync(conversationUrl)).Content.ReadAsStringAsync();
        page.Should().NotContain(new string('b', 2001), "overlong bodies are rejected");
        page.Should().Contain("No messages yet", "nothing invalid was persisted");

        // Boundary body (exactly 2000 chars) is accepted.
        await PostFormAsync(owner, conversationUrl, conversationUrl + "/send",
            new Dictionary<string, string> { ["body"] = new string('c', 2000) });
        page = await (await owner.GetAsync(conversationUrl)).Content.ReadAsStringAsync();
        page.Should().Contain(new string('c', 2000), "the 2000-character boundary is accepted");
    }
}
