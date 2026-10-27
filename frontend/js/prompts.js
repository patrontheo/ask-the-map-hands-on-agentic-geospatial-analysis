// Example prompts for the prompt library (follow-ups come from the model, via suggest_follow_ups). Edit freely: each group is a heading, an optional hint and its prompts.
export const PROMPT_GROUPS = [
  {
    title: "Screening",
    prompts: [
      "Which sites lie inside the wildfire footprint, and how many distinct sites is that?",
      "What TIV do the sites in the footprint represent, and which companies have the highest exposed TIV?",
      "For each company, what share of its portfolio TIV is inside the footprint?",
    ],
  },
  {
    title: "Communes",
    prompts: [
      "Which commune has the highest percentage of its area burnt by the wildfire?",
      "How much of Arès was burnt by the wildfire, in hectares and as a percentage of its total area?",
    ],
  },
  {
    title: "Explore the data",
    prompts: [
      "Describe the portfolio: how many sites and companies are there, and what is the total TIV?",
      "Which communes have the most sites?",
      "Show me the sites of Halvorne Logistics on the map.",
    ],
  },
  {
    title: "Trick questions",
    hint: "Watch how the answer handles ambiguity.",
    prompts: [
      "Which company is most affected by the wildfire?",
      "How much has been lost in the fire?",
    ],
  },
];
