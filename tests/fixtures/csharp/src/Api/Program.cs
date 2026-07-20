using System;
using Microsoft.AspNetCore.Builder;
using Demo.Domain;

namespace Demo.Api;

/// <summary>Application entry point.</summary>
public class Program
{
    public static void Main(string[] args)
    {
        var builder = WebApplication.CreateBuilder(args);
        builder.Services.AddSingleton<GreetingService>();
        var app = builder.Build();

        app.MapGet("/health", () => "ok");

        app.Run();
    }
}
