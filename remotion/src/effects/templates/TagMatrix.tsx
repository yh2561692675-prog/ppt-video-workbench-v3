export function TagMatrix({ tags }: { tags: string[] }) {
  const groups: string[][] = [];
  for (let index = 0; index < tags.length; index += 5) groups.push(tags.slice(index, index + 5));
  return (
    <div className="tag-matrix">
      {groups.map((group, index) => (
        <div key={index} className="tag-matrix__group" data-group-size={group.length}>
          {group.map((tag) => (
            <span key={tag}>{tag}</span>
          ))}
        </div>
      ))}
    </div>
  );
}
